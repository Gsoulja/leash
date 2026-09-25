// Composer: suggested replies (real buttons, ≥ 44px; at most one ink-filled), a text field and a send button that
// is disabled until there is something to send.
import { useState, type FormEvent } from "react";
import { Icon, type IconName } from "../icons";

export type Reply = { label: string; primary?: boolean; icon?: IconName; disabled?: boolean };

export function Composer({ replies, onReply, onSend, disabled = false, placeholder = "Message the permission assistant…",
                          fieldLabel = "Message", sendLabel = "Send", field = true }: {
  replies: Reply[]; onReply: (label: string) => void; onSend: (text: string) => void; disabled?: boolean; placeholder?: string;
  /** Accessible names of the field and the send button. */
  fieldLabel?: string; sendLabel?: string;
  /** false: suggested replies only, for a step that takes no free text (e.g. consent). */
  field?: boolean;
}) {
  const [text, setText] = useState("");
  const ready = !disabled && text.trim() !== "";
  function submit(e: FormEvent) {
    e.preventDefault();
    if (!ready) return;
    onSend(text.trim());
    setText("");
  }
  return (
    <div className="composer">
      {replies.length > 0 && (
        <div className="replies">
          {replies.map((r) => (
            <button key={r.label} type="button" className={`reply${r.primary ? " primary" : ""}`} disabled={disabled || r.disabled}
                    onClick={() => onReply(r.label)}>{r.icon && <Icon name={r.icon} />}{r.label}</button>
          ))}
        </div>
      )}
      {field && <form className="compose-row" onSubmit={submit}>
        <input className="compose-field" aria-label={fieldLabel} placeholder={placeholder} value={text} disabled={disabled}
               onChange={(e) => setText(e.target.value)} />
        <button type="submit" className="send" aria-label={sendLabel} disabled={!ready}><Icon name="send" /></button>
      </form>}
    </div>
  );
}
