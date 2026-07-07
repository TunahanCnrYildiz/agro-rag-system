import React from "react";
import { StyleSheet, Text, View } from "react-native";
import { colors } from "./theme";

// Minimal markdown renderer for LLM-style chat output: **bold**, *italic*,
// and "* "/"- " bullet lines. React Native has no innerHTML, so markdown is
// parsed into blocks and rendered as nested Text/View components.

interface Segment {
  text: string;
  bold: boolean;
  italic: boolean;
}

function parseInline(line: string): Segment[] {
  const segments: Segment[] = [];
  // Bold first (**...**), then remaining single-asterisk pairs as italic.
  const tokens = line.split(/(\*\*.+?\*\*)/g);
  for (const token of tokens) {
    if (token.startsWith("**") && token.endsWith("**") && token.length > 3) {
      segments.push({ text: token.slice(2, -2), bold: true, italic: false });
      continue;
    }
    const subTokens = token.split(/(\*.+?\*)/g);
    for (const sub of subTokens) {
      if (sub.startsWith("*") && sub.endsWith("*") && sub.length > 1) {
        segments.push({ text: sub.slice(1, -1), bold: false, italic: true });
      } else if (sub) {
        segments.push({ text: sub, bold: false, italic: false });
      }
    }
  }
  return segments;
}

type Block =
  | { type: "paragraph"; segments: Segment[] }
  | { type: "list"; items: Segment[][] };

function parseBlocks(text: string): Block[] {
  const lines = text.split("\n");
  const blocks: Block[] = [];
  let currentList: Segment[][] | null = null;

  for (const line of lines) {
    const bulletMatch = /^\s*[*-]\s+(.*)$/.exec(line);
    if (bulletMatch) {
      if (!currentList) {
        currentList = [];
        blocks.push({ type: "list", items: currentList });
      }
      currentList.push(parseInline(bulletMatch[1]));
    } else {
      currentList = null;
      if (line.trim() !== "") {
        blocks.push({ type: "paragraph", segments: parseInline(line) });
      }
    }
  }
  return blocks;
}

function renderSegments(segments: Segment[], baseStyle: object) {
  return segments.map((seg, i) => (
    <Text
      key={i}
      style={[
        baseStyle,
        seg.bold && styles.bold,
        seg.italic && styles.italic,
      ]}
    >
      {seg.text}
    </Text>
  ));
}

export function MarkdownText({ text, color }: { text: string; color: string }) {
  const blocks = parseBlocks(text);
  const baseStyle = { color };
  return (
    <View>
      {blocks.map((block, i) => {
        if (block.type === "paragraph") {
          return (
            <Text key={i} style={[styles.paragraph, baseStyle]}>
              {renderSegments(block.segments, baseStyle)}
            </Text>
          );
        }
        return (
          <View key={i} style={styles.list}>
            {block.items.map((item, j) => (
              <View key={j} style={styles.listRow}>
                <Text style={[styles.bullet, baseStyle]}>{"•"}</Text>
                <Text style={[styles.listText, baseStyle]}>
                  {renderSegments(item, baseStyle)}
                </Text>
              </View>
            ))}
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  paragraph: { fontSize: 13.5, lineHeight: 19, marginBottom: 8 },
  list: { marginBottom: 8 },
  listRow: { flexDirection: "row", marginBottom: 4, paddingRight: 4 },
  bullet: { fontSize: 13.5, lineHeight: 19, marginRight: 6, color: colors.green },
  listText: { fontSize: 13.5, lineHeight: 19, flex: 1 },
  bold: { fontWeight: "700" },
  italic: { fontStyle: "italic" },
});
