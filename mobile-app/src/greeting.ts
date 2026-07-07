// Greeting shown before any user message exists, so there's nothing to
// detect language from yet - picked from the device locale instead. Falls
// back to English for locales not in this list. Mirrors the web widget's
// greeting set (web-widget/widget/agro-chat-widget.js) for consistency.
const GREETINGS: Record<string, string> = {
  tr: "Merhaba! Ben ekolojik tarım asistanıyım. Bitki besleme, organik gübreleme ve toprak sağlığı hakkında sorularınızı yanıtlayabilirim.",
  en: "Hello! I'm an ecological agriculture assistant. I can help with plant nutrition, organic fertilization, and soil health questions.",
  de: "Hallo! Ich bin ein Assistent für ökologische Landwirtschaft. Ich helfe gerne bei Fragen zu Pflanzenernährung, organischer Düngung und Bodengesundheit.",
  fr: "Bonjour ! Je suis un assistant en agriculture écologique. Je peux répondre à vos questions sur la nutrition des plantes, la fertilisation biologique et la santé des sols.",
  es: "¡Hola! Soy un asistente de agricultura ecológica. Puedo ayudarte con preguntas sobre nutrición vegetal, fertilización orgánica y salud del suelo.",
  ar: "مرحباً! أنا مساعد للزراعة البيئية. يمكنني مساعدتك في أسئلة حول تغذية النباتات والتسميد العضوي وصحة التربة.",
};

export function getGreeting(): string {
  let locale = "en";
  try {
    locale = Intl.NumberFormat().resolvedOptions().locale || "en";
  } catch {
    // Intl unavailable — fall back to English.
  }
  const lang = locale.slice(0, 2).toLowerCase();
  return GREETINGS[lang] || GREETINGS.en;
}
