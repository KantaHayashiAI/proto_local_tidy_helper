const ja = {
  title: "ローカル片付け支援AI",
  subtitle: "固定視点の観測とローカルVLMで、次の一手を提案します",
  save: "保存",
  validate: "接続確認",
  runNow: "今すぐ観測",
  diagnostics: "診断",
  history: "履歴",
  tasks: "次の一手",
  setup: "セットアップ"
};

const en = {
  title: "Local Tidy Helper",
  subtitle: "Stationary vision, local VLM, and next-step guidance",
  save: "Save",
  validate: "Validate",
  runNow: "Run now",
  diagnostics: "Diagnostics",
  history: "History",
  tasks: "Next move",
  setup: "Setup"
};

export type Locale = "ja" | "en";

export function copyForLocale(locale: Locale) {
  return locale === "en" ? en : ja;
}
