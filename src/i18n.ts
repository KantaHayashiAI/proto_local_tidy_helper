const ja = {
  title: "部屋が、そっと声をかける",
  subtitle: "定点観測 × ローカルVLM × プッシュ型片付け支援",
  save: "保存",
  validate: "接続診断",
  runNow: "今すぐ観測",
  diagnostics: "診断",
  history: "履歴",
  tasks: "次の一手",
  setup: "セットアップ"
};

const en = {
  title: "The room gently speaks",
  subtitle: "Stationary vision, local VLM, and push-based tidy coaching",
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
