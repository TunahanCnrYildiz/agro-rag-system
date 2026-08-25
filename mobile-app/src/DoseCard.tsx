// The product-dose card. Three inputs and nothing else: the product, the crop
// group, and the area with a unit selector - the same unit-as-SELECTION rule
// the budget card follows.
//
// There is deliberately NO application-method control. Of the 42 products with
// a per-area dose, 37 publish it for drip irrigation only, so a method selector
// would offer a choice in appearance only - and pressing the wrong half would
// say we hold no figure for a method the maker never published one for. The
// method is reported in the answer instead.
import React, { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { DoseFormSpec, DosePayload } from "./api";
import { colors } from "./theme";
// Shared with BudgetCard: typing "higro" has to find "HİGRO", and the dotted
// I is exactly what a plain toLowerCase() gets wrong.
import { fold } from "./turkish";

interface Props {
  form: DoseFormSpec;
  // `summary` is what the chat shows as the user's bubble for this turn. The
  // request still carries the original question, but echoing it again would
  // read as the user asking twice.
  onSubmit: (payload: DosePayload, summary: string) => void;
  // A stale card from an earlier turn stays rendered and tappable, so it needs
  // the same submit gate as the text input.
  disabled: boolean;
}

export default function DoseCard({ form, onSubmit, disabled }: Props) {
  const [product, setProduct] = useState(form.product);
  const [query, setQuery] = useState(form.product);
  const [group, setGroup] = useState(form.group);
  const [area, setArea] = useState(form.area.value);
  const [unit, setUnit] = useState(form.area.unit);

  // The list closes when the box already reads as the chosen product and
  // reopens the moment the text differs - the budget card's rule.
  const searchOpen = Boolean(query.trim() && query !== product);
  const matches = searchOpen
    ? form.products.filter((p) => fold(p).includes(fold(query))).slice(0, 8)
    : [];

  function submit() {
    if (disabled) return;
    const payload: DosePayload = {
      product,
      group,
      area: { value: area.trim(), unit },
    };
    const groupLabel = form.groups.find((g) => g.id === group)?.label ?? "";
    const unitLabel = form.area.units.find((u) => u.id === unit)?.label ?? "";
    const summary = [product, groupLabel, `${area.trim()} ${unitLabel}`.trim()]
      .filter(Boolean)
      .join(" · ");
    onSubmit(payload, summary);
  }

  return (
    <View style={styles.card}>
      <View style={styles.row}>
        <Text style={styles.label}>Ürün</Text>
        <TextInput
          style={styles.input}
          value={query}
          onChangeText={setQuery}
          placeholder="Ürün arayın (örn. higro)"
          placeholderTextColor="#9aa"
        />
        {matches.map((name) => (
          <Pressable
            key={name}
            style={styles.match}
            onPress={() => {
              setProduct(name);
              setQuery(name);
            }}
          >
            <Text style={styles.matchText}>{name}</Text>
          </Pressable>
        ))}
        {form.errors.product ? (
          <Text style={styles.error}>{form.errors.product}</Text>
        ) : null}
      </View>

      <View style={styles.row}>
        <Text style={styles.label}>Grup</Text>
        <View style={styles.units}>
          {form.groups.map((g) => (
            <Pressable
              key={g.id}
              onPress={() => setGroup(g.id)}
              style={[styles.unit, group === g.id && styles.unitActive]}
            >
              <Text style={[styles.unitText, group === g.id && styles.unitTextActive]}>
                {g.label}
              </Text>
            </Pressable>
          ))}
        </View>
        {form.errors.group ? (
          <Text style={styles.error}>{form.errors.group}</Text>
        ) : null}
      </View>

      <View style={styles.row}>
        <Text style={styles.label}>{form.area.label}</Text>
        <View style={styles.inputRow}>
          <TextInput
            style={styles.input}
            keyboardType="numeric"
            value={area}
            onChangeText={setArea}
            placeholder="0"
            placeholderTextColor="#9aa"
          />
          <View style={styles.units}>
            {form.area.units.map((u) => (
              <Pressable
                key={u.id}
                onPress={() => setUnit(u.id)}
                style={[styles.unit, unit === u.id && styles.unitActive]}
              >
                <Text style={[styles.unitText, unit === u.id && styles.unitTextActive]}>
                  {u.label}
                </Text>
              </Pressable>
            ))}
          </View>
        </View>
        {form.errors.area ? <Text style={styles.error}>{form.errors.area}</Text> : null}
      </View>

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
  units: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
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
