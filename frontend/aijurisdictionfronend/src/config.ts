export const azureSpeechConfig = {
  key: import.meta.env.VITE_AZURE_SPEECH_KEY ?? "",
  region: import.meta.env.VITE_AZURE_SPEECH_REGION ?? "",
  voice: import.meta.env.VITE_AZURE_SPEECH_VOICE ?? "en-US-JennyNeural"
};

export const isAzureSpeechConfigured = Boolean(
  azureSpeechConfig.key && azureSpeechConfig.region
);
