import { useEffect, useRef, type ReactNode } from "react";
import "./TaskDialog.css";

export function TaskDialog({
  children,
  onClose,
  code,
}: {
  children: ReactNode;
  onClose: () => void;
  code?: string;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const backdropPressed = useRef(false);
  useEffect(() => {
    const element = dialog.current!;
    const previousFocus = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    element.showModal();
    return () => {
      element.close();
      document.body.style.overflow = overflow;
      const target = previousFocus?.isConnected
        ? previousFocus
        : document.getElementById("conteudo");
      target?.focus({ preventScroll: true });
    };
  }, []);
  const outside = (x: number, y: number) => {
    const rect = dialog.current!.getBoundingClientRect();
    return x < rect.left || x > rect.right || y < rect.top || y > rect.bottom;
  };
  return (
    <dialog
      ref={dialog}
      className="task-dialog"
      aria-label="Detalhes da tarefa"
      onKeyDown={(e) => {
        if (e.key !== "Tab") return;
        const controls = [
          ...e.currentTarget.querySelectorAll<HTMLElement>(
            'button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="0"]',
          ),
        ].filter((element) => element.getClientRects().length > 0);
        const first = controls[0],
          last = controls.at(-1);
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onPointerDown={(e) => {
        backdropPressed.current =
          e.target === e.currentTarget && outside(e.clientX, e.clientY);
      }}
      onClick={(e) => {
        if (
          backdropPressed.current &&
          e.target === e.currentTarget &&
          outside(e.clientX, e.clientY)
        )
          onClose();
        backdropPressed.current = false;
      }}
    >
      <header className="task-dialog__bar">
        <div>
          <span className="eyebrow">TAREFA</span>
          {code && <strong>{code}</strong>}
        </div>
        <button
          type="button"
          className="task-dialog__close"
          aria-label="Fechar tarefa"
          onClick={() => onClose()}
          autoFocus
        >
          <span aria-hidden="true">×</span>
        </button>
      </header>
      <div className="task-dialog__scroll">{children}</div>
    </dialog>
  );
}
