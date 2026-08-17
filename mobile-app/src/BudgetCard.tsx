// The budget form, rendered inline in the chat. Every field carries a unit
// selector because the unit has to be a SELECTION: a farmer who harvested 2
// tons from 5 donum thinks "2 ton", and typing that into a per-dekar field
// would be five times too high and completely silent.
import React, { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { BudgetPayload, FormSpec } from "./api";
import { colors } from "./theme";

interface Props {
  form: FormSpec;
  // `summary` is what the chat shows as the user's bubble for this turn. The
  // request still carries the original question, but echoing it again would
  // read as the user asking twice.
  onSubmit: (payload: BudgetPayload, summary: string) => void;
}

export default function BudgetCard({ form, onSubmit }: Props) {
  // Seeded from the server's `value`, which is empty in P1 and prefilled by the
  // norm layer in P2 - so this card needs no change when that lands.
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(form.fields.map((f) => [f.id, f.value]))
  );
  const [units, setUnits] = useState<Record<string, string>>(() =>
    Object.fromEntries(form.fields.map((f) => [f.id, f.units[0].id]))
  );

  function submit() {
    const payload: Record<string, { value: string; unit: string }> = {};
    const parts: string[] = [];
    for (const f of form.fields) {
      const v = (values[f.id] ?? "").trim();
      if (!v) continue;
      payload[f.id] = { value: v, unit: units[f.id] };
      const unit = f.units.find((u) => u.id === units[f.id]);
      parts.push(`${f.label}: ${v} ${unit ? unit.label : ""}`.trim());
    }
    onSubmit(payload as BudgetPayload, parts.join(" · "));
  }

  return (
    <View style={styles.card}>
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
              onChangeText={(t) => setValues((p) => ({ ...p, [f.id]: t }))}
              placeholder="0"
              placeholderTextColor="#9aa"
            />
            <View style={styles.units}>
              {f.units.map((u) => (
                <Pressable
                  key={u.id}
                  onPress={() => setUnits((p) => ({ ...p, [f.id]: u.id }))}
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
          {f.error ? <Text style={styles.error}>{f.error}</Text> : null}
        </View>
      ))}
      <Pressable style={styles.submit} onPress={submit}>
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
  submit: {
    backgroundColor: colors.green,
    borderRadius: 8,
    paddingVertical: 11,
    alignItems: "center",
  },
  submitText: { color: "#fff", fontWeight: "700" },
});
