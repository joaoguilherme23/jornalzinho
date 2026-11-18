import { appHref } from "../lib/navigation";
import Markdown, { defaultUrlTransform } from "react-markdown";
import type { Root, RootContent, PhrasingContent } from "mdast";
import "./TaskMarkdown.css";

const taskCode = /\b[A-Z][A-Z0-9_]*-\d+\b/g;
const skip = new Set([
  "code",
  "inlineCode",
  "link",
  "linkReference",
  "html",
  "image",
  "imageReference",
]);

export function TaskMarkdown({
  text,
  resolved = new Map(),
  boardId,
}: {
  text: string;
  resolved?: ReadonlyMap<string, boolean>;
  boardId?: number;
}) {
  // Transform text nodes only. Code, existing links and raw HTML keep their meaning.
  const references = () => (tree: Root) => {
    function visit(parent: Root | RootContent) {
      if (skip.has(parent.type) || !("children" in parent)) return;
      const children: RootContent[] = [];
      for (const child of parent.children) {
        if (child.type !== "text") {
          visit(child);
          children.push(child);
          continue;
        }
        let offset = 0;
        const pieces: PhrasingContent[] = [];
        for (const match of child.value.matchAll(taskCode)) {
          if (!resolved.get(match[0])) continue;
          if (match.index > offset)
            pieces.push({
              type: "text",
              value: child.value.slice(offset, match.index),
            });
          pieces.push({
            type: "link",
            url: appHref(
              `#/task/${encodeURIComponent(match[0])}${boardId ? `?board=${boardId}` : ""}`,
            ),
            children: [{ type: "text", value: match[0] }],
          });
          offset = match.index + match[0].length;
        }
        if (!offset) children.push(child);
        else {
          if (offset < child.value.length)
            pieces.push({ type: "text", value: child.value.slice(offset) });
          children.push(...pieces);
        }
      }
      // Each replacement preserves the text node's allowed phrasing content.
      parent.children = children as typeof parent.children;
    }
    visit(tree);
  };
  return (
    <div className="task-markdown">
      <Markdown
        skipHtml
        remarkPlugins={[references]}
        disallowedElements={["img"]}
        urlTransform={(value) => {
          const safe = defaultUrlTransform(value);
          if (/^[a-z][a-z\d+.-]*:/i.test(safe) && !/^https?:/i.test(safe))
            return "";
          return safe;
        }}
        components={{
          a: ({ node: _node, children, href, ...props }) =>
            href ? (
              <a href={href} {...props}>
                {children}
              </a>
            ) : (
              <span>{children}</span>
            ),
        }}
      >
        {text}
      </Markdown>
    </div>
  );
}
