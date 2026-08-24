interface Props {
  isRecording: boolean;
  disabled?: boolean;
  onStart: () => void;
  onStop: () => void;
}

export function RecordButton({ isRecording, disabled, onStart, onStop }: Props) {
  return (
    <button
      className={`record-button ${isRecording ? "recording" : ""}`}
      onClick={isRecording ? onStop : onStart}
      disabled={disabled}
      aria-pressed={isRecording}
    >
      <span className="record-dot" aria-hidden="true" />
      {isRecording ? "Stop" : "Start listening"}
    </button>
  );
}
