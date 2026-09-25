// Chat header (handoff V4, DEC-044 ruling 6): the assistant is the "Permission assistant", and its status line only
// ever says setting up / active / revoked — it never searches or shops (DEC-033).
import { LogoMark, type LogoStatus } from "../LogoMark";

const LINE: Record<LogoStatus, string> = { none: "Setting up your permission", active: "Permission active", revoked: "Permission revoked" };

export function ChatHeader({ status }: { status: LogoStatus }) {
  return (
    <header className="chat-head" aria-label="Permission assistant">
      <LogoMark status={status} size={30} />
      <div>
        <div className="chat-name">Permission assistant</div>
        <div className={`chat-status ${status}`}>{LINE[status]}</div>
      </div>
    </header>
  );
}
