// The crop-comparison card: two searchable selects and nothing else.
//
// There is no area field on purpose - area applies the same multiplier to both
// crops, so it cannot change the comparison, and every figure stays per dekar.
import React, { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { CompareCrop, CompareFormSpec, ComparePayload } from "./api";
import { colors } from "./theme";
import { fold } from "./turkish";

interface Props {
  form: CompareFormSpec;
  // `summary` is what the chat shows as the user's bubble for this turn.
  onSubmit: (payload: ComparePayload, summary: string) => void;
  disabled: boolean;
}

function labelOf(form: CompareFormSpec, id: string): string {
  return form.crops.find((c) => c.id === id)?.label ?? "";
}

export default function CompareCard({ form, onSubmit, disabled }: Props) {
  const [first, setFirst] = useState(form.first);
  const [second, setSecond] = useState(form.second);
  const [queryOne, setQueryOne] = useState(labelOf(form, form.first));
  const [queryTwo, setQueryTwo] = useState(labelOf(form, form.second));

  function matches(query: string, chosen: string): CompareCrop[] {
    const open = Boolean(query.trim() && query !== labelOf(form, chosen));
    if (!open) return [];
    return form.crops
      .filter((c) => fold(c.label).includes(fold(query)))
      .slice(0, 8);
  }

  function submit() {
    if (disabled) return;
    const summary = [labelOf(form, first), labelOf(form, second)]
      .filter(Boolean)
      .join(" ↔ ");
    onSubmit({ first, second }, summary || "karşılaştır");
  }

  function select(
    slot: "first" | "second",
    option: CompareCrop,
  ) {
    if (slot === "first") {
      setFirst(option.id);
      setQueryOne(option.label);
    } else {
      setSecond(option.id);
      setQueryTwo(option.label);
    }
  }

  const rows: {
    slot: "first" | "second";
    label: string;
    query: string;
    setQuery: (t: string) => void;
    chosen: string;
    error: string | null;
  }[] = [
    { slot: "first", label: "Birinci ürün", query: queryOne, setQuery: setQueryOne, chosen: first, error: form.errors.first },
    { slot: "second", label: "İkinci ürün", query: queryTwo, setQuery: setQueryTwo, chosen: second, error: form.errors.second },
  ];

  return (
    <View style={styles.card}>
      {form.province ? (
        <Text style={styles.note}>{form.province} için yayımlanmış rakamlar</Text>
      ) : null}
      {rows.map((row) => (
        <View key={row.slot} style={styles.row}>
          <Text style={styles.label}>{row.label}</Text>
          <TextInput
            style={styles.input}
            value={row.query}
            onChangeText={row.setQuery}
            placeholder="Ürün arayın (örn. domates)"
            placeholderTextColor="#9aa"
          />
          {matches(row.query, row.chosen).map((option) => (
            <Pressable
              key={option.id}
              style={styles.match}
              onPress={() => select(row.slot, option)}
            >
              <Text style={styles.matchText}>{option.label}</Text>
            </Pressable>
          ))}
          {row.error ? <Text style={styles.error}>{row.error}</Text> : null}
        </View>
      ))}
      <Pressable
        style={[styles.submit, disabled && styles.submitDisabled]}
        onPress={submit}
        disabled={disabled}
      >
        <Text style={styles.submitText}>Karşılaştır</Text>
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
  note: { fontSize: 11, color: "#6b7a6b" },
  input: {
    borderWidth: 1,
    borderColor: "#e2e8e2",
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 8,
    color: colors.dark,
  },
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
