// The budget form, rendered inline in the chat. Every field carries a unit
// selector because the unit has to be a SELECTION: a farmer who harvested 2
// tons from 5 donum thinks "2 ton", and typing that into a per-dekar field
// would be five times too high and completely silent.
import React, { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { BudgetPayload, CropOption, FormSpec, NormCell } from "./api";
import { colors } from "./theme";

// Turkish lowercasing, so typing "findik" finds "Fındık". toLowerCase() alone
// maps I to i but leaves I undotted, and the crops the user searches for most
// are the ones with dotted capitals.
function fold(text: string): string {
  return text
    .replace(/I/g, "ı")
    .replace(/İ/g, "i")
    .toLowerCase()
    .replace(/[ışğüöç]/g, (c) => ({ ı: "i", ş: "s", ğ: "g", ü: "u", ö: "o", ç: "c" }[c] ?? c));
}

interface Props {
  form: FormSpec;
  // `summary` is what the chat shows as the user's bubble for this turn. The
  // request still carries the original question, but echoing it again would
  // read as the user asking twice.
  onSubmit: (payload: BudgetPayload, summary: string) => void;
  // Mirrors the chat screen's `loading`: a stale card from an earlier turn
  // stays rendered and tappable, so it needs the same submit gate as the
  // text input/send button.
  disabled: boolean;
}

export default function BudgetCard({ form, onSubmit, disabled }: Props) {
  // Seeded from the server's `value`, which is empty in P1 and prefilled by the
  // norm layer in P2 - so this card needs no change when that lands.
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(form.fields.map((f) => [f.id, f.value]))
  );
  // A rejected form echoes back the unit the farmer had selected; fall back to
  // the field's first unit otherwise. Without this a rejection would snap
  // every chip back to its default and silently contradict the value sitting
  // next to it.
  const [units, setUnits] = useState<Record<string, string>>(() =>
    Object.fromEntries(form.fields.map((f) => [f.id, f.unit ?? f.units[0].id]))
  );
  // Resolved once, from props, so both initializers below agree on which
  // crop (if any) the rejected form was echoing back.
  const echoedCrop = form.crop
    ? (form.crops ?? []).find((c) => c.id === form.crop)
    : undefined;
  // A rejected form names its crop by id only; the search box needs the
  // label to show something other than blank.
  const [query, setQuery] = useState(() => echoedCrop?.label ?? "");
  const [crop, setCrop] = useState<string | undefined>(form.crop);
  // Without this, a rejected form re-displays with every field unmarked, so
  // the next submit sends source: "user" for a figure that is still TÜİK's -
  // and the answer then claims the whole estimate rests on numbers the
  // farmer typed, when one of them never was. Seeded straight from the
  // server's echoed `source`, not by comparing the echoed value and unit to
  // the selected crop's cell: that comparison used to mark a field "norm"
  // whenever a farmer's own typed number happened to equal the norm, which
  // then had the next submit claim their own figure as TÜİK's.
  const [sources, setSources] = useState<Record<string, "norm" | "user">>(() => {
    const result: Record<string, "norm" | "user"> = {};
    for (const f of form.fields) {
      if (f.source === "norm") result[f.id] = "norm";
    }
    return result;
  });

  const selected = (form.crops ?? []).find((c) => c.id === crop);
  // The list closes when the box already reads as the chosen crop, and reopens
  // the moment the text differs. Clearing `crop` on every keystroke instead
  // would blank the provenance lines under fields that are still showing its
  // figures.
  const searchOpen = Boolean(query.trim() && query !== selected?.label);
  const matches = searchOpen
    ? (form.crops ?? []).filter((c) => fold(c.label).includes(fold(query))).slice(0, 8)
    : [];

  // The wire carries exactly one `crop`, so a field's "norm" marking can only
  // ever belong to the currently selected crop. The moment the farmer picks a
  // different crop - or says theirs isn't in the list - the previous crop's
  // regional average is meaningless. Leaving the number on screen would
  // silently convert TÜİK's figure into the farmer's own, because once `crop`
  // changes nothing downstream can still attribute it: the server fails
  // closed and downgrades the field to "user", and the answer would then
  // claim a TÜİK figure rests entirely on numbers the farmer typed. So any
  // field still marked "norm" that `newCrop` cannot refill is cleared here -
  // value, marking and unit all reset - before selection proceeds. Fields the
  // farmer typed into (source "user", or never marked) are never touched.
  function clearUnfillableNorms(newCrop: CropOption | undefined) {
    const cellFor: Record<string, NormCell | null | undefined> = {
      yield_total: newCrop?.yield,
      price: newCrop?.price,
    };
    for (const [id, cell] of Object.entries(cellFor)) {
      if (sources[id] !== "norm") continue;
      if (cell) continue; // the new crop can refill it; the caller does that next
      const field = form.fields.find((f) => f.id === id);
      if (!field) continue;
      setValues((p) => ({ ...p, [id]: "" }));
      setUnits((p) => ({ ...p, [id]: field.units[0].id }));
      setSources((p) => {
        const next = { ...p };
        delete next[id];
        return next;
      });
    }
  }

  function selectCrop(option: CropOption) {
    setCrop(option.id);
    setQuery(option.label);
    clearUnfillableNorms(option);
    const cells: [string, NormCell | null][] = [
      ["yield_total", option.yield],
      ["price", option.price],
    ];
    for (const [id, cell] of cells) {
      if (!cell) continue;
      // Only fields still marked as a norm are replaced. A figure the farmer
      // typed is not thrown away because they browsed the crop list.
      if (sources[id] === "user") continue;
      setValues((p) => ({ ...p, [id]: cell.value }));
      // The unit travels with the value: 28,4 under a "kg" chip would claim a
      // whole orchard yielded 28 kilos.
      setUnits((p) => ({ ...p, [id]: cell.unit }));
      setSources((p) => ({ ...p, [id]: "norm" }));
    }
  }

  function submit() {
    if (disabled) return;
    const payload: Record<string, { value: string; unit: string; source: "norm" | "user" }> &
      Pick<BudgetPayload, "crop"> = {};
    const parts: string[] = [];
    for (const f of form.fields) {
      const v = (values[f.id] ?? "").trim();
      if (!v) continue;
      payload[f.id] = { value: v, unit: units[f.id], source: sources[f.id] ?? "user" };
      const unit = f.units.find((u) => u.id === units[f.id]);
      parts.push(`${f.label}: ${v} ${unit ? unit.label : ""}`.trim());
    }
    if (crop) payload.crop = crop;
    onSubmit(payload, parts.join(" · "));
  }

  return (
    <View style={styles.card}>
      {form.crops && form.crops.length > 0 && (
        <View style={styles.row}>
          <Text style={styles.label}>Ürün</Text>
          <TextInput
            style={styles.input}
            value={query}
            onChangeText={setQuery}
            placeholder="Ürün arayın (örn. fındık)"
            placeholderTextColor="#9aa"
          />
          {matches.map((option) => (
            <Pressable
              key={option.id}
              style={styles.match}
              onPress={() => selectCrop(option)}
            >
              <Text style={styles.matchText}>{option.label}</Text>
            </Pressable>
          ))}
          {searchOpen && (
            // The explicit way out: a crop we do not carry, or one the farmer
            // would rather fill in themselves. It selects nothing and prefills
            // nothing. Shown whenever the box has text and the list is open -
            // not only when something matched - or a search that finds
            // nothing would leave no way out at all.
            <Pressable
              style={styles.match}
              onPress={() => {
                clearUnfillableNorms(undefined);
                setCrop(undefined);
                setQuery("");
              }}
            >
              <Text style={styles.matchText}>Diğer (listede yok)</Text>
            </Pressable>
          )}
        </View>
      )}
      {form.fields.map((f) => (
        <View key={f.id} style={styles.row}>
          <Text style={styles.label}>
            {f.label}
            {f.required ? "" : " (isteğe bağlı)"}
          </Text>
          <View style={styles.inputRow}>
            <TextInput
              style={styles.input}
              keyboardType="numeric"
              value={values[f.id] ?? ""}
              onChangeText={(t) => {
                setValues((p) => ({ ...p, [f.id]: t }));
                setSources((p) => ({ ...p, [f.id]: "user" }));
              }}
              placeholder="0"
              placeholderTextColor="#9aa"
            />
            <View style={styles.units}>
              {f.units.map((u) => (
                <Pressable
                  key={u.id}
                  onPress={() => {
                    // Pressing the already-active unit is a no-op click; it
                    // must not discard a prefilled field's provenance.
                    if (units[f.id] === u.id) return;
                    setUnits((p) => ({ ...p, [f.id]: u.id }));
                    setSources((p) => ({ ...p, [f.id]: "user" }));
                  }}
                  style={[
                    styles.unit,
                    units[f.id] === u.id && styles.unitActive,
                  ]}
                >
                  <Text
                    style={[
                      styles.unitText,
                      units[f.id] === u.id && styles.unitTextActive,
                    ]}
                  >
                    {u.label}
                  </Text>
                </Pressable>
              ))}
            </View>
          </View>
          {f.error ? (
            <Text style={styles.error}>{f.error}</Text>
          ) : (
            sources[f.id] === "norm" && (() => {
              const cell = f.id === "yield_total" ? selected?.yield : f.id === "price" ? selected?.price : null;
              if (!cell) return null;
              return (
                <View>
                  <Text style={styles.note}>{cell.note}</Text>
                  {cell.recent ? <Text style={styles.note}>{cell.recent}</Text> : null}
                </View>
              );
            })()
          )}
        </View>
      ))}
      <Pressable
        style={[styles.submit, disabled && styles.submitDisabled]}
        onPress={submit}
        disabled={disabled}
      >
        <Text style={styles.submitText}>Hesapla</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: "#fff",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#e2e8e2",
    padding: 14,
    marginTop: 8,
    gap: 12,
  },
  row: { gap: 6 },
  label: { fontSize: 13, fontWeight: "600", color: colors.dark },
  inputRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  input: {
    flex: 1,
    borderWidth: 1,
    borderColor: "#e2e8e2",
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 8,
    color: colors.dark,
  },
  units: { flexDirection: "row", gap: 6 },
  unit: {
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#e2e8e2",
  },
  unitActive: { backgroundColor: colors.green, borderColor: colors.green },
  unitText: { fontSize: 12, color: colors.dark },
  unitTextActive: { color: "#fff", fontWeight: "600" },
  error: { fontSize: 12, color: "#c0392b" },
  note: { fontSize: 11, color: "#6b7a6b" },
  match: {
    paddingHorizontal: 10,
    paddingVertical: 9,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#e2e8e2",
  },
  matchText: { fontSize: 13, color: colors.dark },
  submit: {
    backgroundColor: colors.green,
    borderRadius: 8,
    paddingVertical: 11,
    alignItems: "center",
  },
  submitDisabled: { opacity: 0.5 },
  submitText: { color: "#fff", fontWeight: "700" },
});
