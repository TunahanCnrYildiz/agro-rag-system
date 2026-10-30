// The season-calendar card (PDF p5): the crop and the planting date, nothing
// else. Every date in the answer is the server adding FAO-56's published stage
// lengths to this date - the card computes nothing itself.
import React, { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { SeasonFormSpec, SeasonPayload } from "./api";
import { colors } from "./theme";
import { fold } from "./turkish";

interface Props {
  form: SeasonFormSpec;
  onSubmit: (payload: SeasonPayload, summary: string) => void;
  disabled: boolean;
}

/** Today as GG.AA.YYYY - a starting point the farmer edits, not an assumption
 *  about when they plant: the box must hold SOMETHING in the format it asks for. */
function today(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()}`;
}

function labelOf(form: SeasonFormSpec, id: string): string {
  return form.crops.find((c) => c.id === id)?.label ?? "";
}

export default function SeasonCard({ form, onSubmit, disabled }: Props) {
  const [crop, setCrop] = useState(form.crop);
  const [query, setQuery] = useState(labelOf(form, form.crop));
  const [planting, setPlanting] = useState(form.planting || today());
  // A tree is not planted each year: its calendar runs from the season's start.
  const isTree = form.crops.find((c) => c.id === crop)?.kind === "tree";

  // The list closes when the box already reads as the chosen crop - the
  // budget and dose cards' rule.
  const searchOpen = Boolean(query.trim() && query !== labelOf(form, crop));
  const matches = searchOpen
    ? form.crops.filter((c) => fold(c.label).includes(fold(query))).slice(0, 8)
    : [];

  function submit() {
    if (disabled) return;
    const summary = [labelOf(form, crop), planting.trim()].filter(Boolean).join(" · ");
    onSubmit({ crop, planting: planting.trim() }, summary);
  }

  return (
    <View style={styles.card}>
      <View style={styles.row}>
        <Text style={styles.label}>Ürün</Text>
        <TextInput
          style={styles.input}
          value={query}
          onChangeText={setQuery}
          placeholder="Ürün arayın (örn. domates)"
          placeholderTextColor="#9aa"
        />
        {matches.map((c) => (
          <Pressable
            key={c.id}
            style={styles.match}
            onPress={() => {
              setCrop(c.id);
              setQuery(c.label);
            }}
          >
            <Text style={styles.matchText}>{c.label}</Text>
          </Pressable>
        ))}
        {form.errors.crop ? <Text style={styles.error}>{form.errors.crop}</Text> : null}
      </View>

      <View style={styles.row}>
        <Text style={styles.label}>
          {isTree ? "Sezon başlangıcı (uyanma, yaprak açma)" : "Ekim (dikim) tarihi"}
        </Text>
        <TextInput
          style={styles.input}
          value={planting}
          onChangeText={setPlanting}
          placeholder="GG.AA.YYYY"
          placeholderTextColor="#9aa"
          keyboardType="numbers-and-punctuation"
        />
        {form.errors.planting ? (
          <Text style={styles.error}>{form.errors.planting}</Text>
        ) : null}
      </View>

      <Pressable
        style={[styles.submit, disabled && styles.submitDisabled]}
        onPress={submit}
        disabled={disabled}
      >
        <Text style={styles.submitText}>Programı çıkar</Text>
      </Pressable>
    </View>
  );
}

// The dose card's styles, so the cards read as one family.
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
