import { useEffect, useState } from "react";
import { backend } from "../api";
import { TaskMarkdown } from "./TaskMarkdown";

const code = /\b[A-Z][A-Z0-9_]*-\d+\b/g;
export function TaskReferences({
  text,
  boardId,
}: {
  text: string;
  boardId?: number;
}) {
  const [resolved, setResolved] = useState<Map<string, boolean>>(
    () => new Map(),
  );
  useEffect(() => {
    const codes = [...new Set(text.match(code) ?? [])].slice(0, 12);
    let alive = true;
    setResolved(new Map());
    if (!codes.length)
      return () => {
        alive = false;
      };
    void Promise.all(
      codes.map(async (value) => {
        try {
          await backend.taskByCode(value);
          return [value, true] as const;
        } catch {
          return [value, false] as const;
        }
      }),
    ).then((items) => alive && setResolved(new Map(items)));
    return () => {
      alive = false;
    };
  }, [text]);
  return <TaskMarkdown text={text} resolved={resolved} boardId={boardId} />;
}
