import { FormEvent, useCallback, useEffect, useState } from "react";
import { backend, error } from "../api";
import type { Label, LabelColor, Project, ProjectRole } from "../types";

const colors: LabelColor[] = [
  "teal",
  "blue",
  "purple",
  "orange",
  "red",
  "gray",
];
export function LabelsPage({
  project,
  role = "viewer",
}: {
  project: Project;
  role?: ProjectRole | "admin";
}) {
  const [labels, setLabels] = useState<Label[]>([]);
  const [name, setName] = useState("");
  const [color, setColor] = useState<LabelColor>("teal");
  const [editing, setEditing] = useState<Label | null>(null);
  const [notice, setNotice] = useState("");
  const canManage = role === "admin" || role === "manager";
  const load = useCallback(async () => {
    try {
      setLabels(await backend.labels(project.id, true));
    } catch (failure) {
      setNotice(error(failure));
    }
  }, [project.id]);
  useEffect(() => {
    void load();
  }, [load]);
  async function save(event: FormEvent) {
    event.preventDefault();
    if (!canManage) return;
    try {
      await backend.createLabel(project.id, { name: name.trim(), color });
      setName("");
      setNotice("Etiqueta criada.");
      await load();
    } catch (failure) {
      setNotice(error(failure));
    }
  }
  async function archive(label: Label) {
    if (!canManage) return;
    try {
      await backend.patchLabel(label.id, { is_archived: !label.is_archived });
      await load();
    } catch (failure) {
      setNotice(error(failure));
    }
  }
  async function update(event: FormEvent) {
    event.preventDefault();
    if (!canManage || !editing) return;
    try {
      await backend.patchLabel(editing.id, {
        name: editing.name.trim(),
        color: editing.color,
      });
      setEditing(null);
      setNotice("Etiqueta atualizada.");
      await load();
    } catch (failure) {
      setNotice(error(failure));
    }
  }
  return (
    <section className="labels-page card">
      <p className="eyebrow">{project.key} · catálogo</p>
      <h1>Etiquetas</h1>
      {notice && (
        <p className="error" role="status">
          {notice}
        </p>
      )}
      {canManage ? (
        <form className="form-grid" onSubmit={save}>
          <label>
            Nome
            <input
              required
              maxLength={80}
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <label>
            Cor
            <select
              value={color}
              onChange={(event) => setColor(event.target.value as LabelColor)}
            >
              {colors.map((item) => (
                <option key={item}>{item}</option>
              ))}
            </select>
          </label>
          <button>Criar etiqueta</button>
        </form>
      ) : (
        <p className="readonly">
          Você pode consultar as etiquetas deste projeto.
        </p>
      )}
      <ul className="label-catalog">
        {labels.map((label) => (
          <li key={label.id}>
            <span className={`task-label task-label--${label.color}`}>
              {label.name}
            </span>
            {label.is_archived && <small> Arquivada</small>}
            {canManage && (
              <>
                <button
                  className="quiet"
                  onClick={() => setEditing({ ...label })}
                >
                  Editar
                </button>
                <button className="quiet" onClick={() => void archive(label)}>
                  {label.is_archived ? "Reativar" : "Arquivar"}
                </button>
              </>
            )}
            {editing?.id === label.id && (
              <form className="form-grid" onSubmit={update}>
                <label>
                  Nome
                  <input
                    required
                    maxLength={80}
                    value={editing.name}
                    onChange={(event) =>
                      setEditing({ ...editing, name: event.target.value })
                    }
                  />
                </label>
                <label>
                  Cor
                  <select
                    value={editing.color}
                    onChange={(event) =>
                      setEditing({
                        ...editing,
                        color: event.target.value as LabelColor,
                      })
                    }
                  >
                    {colors.map((item) => (
                      <option key={item}>{item}</option>
                    ))}
                  </select>
                </label>
                <button>Salvar etiqueta</button>
                <button
                  className="quiet"
                  type="button"
                  onClick={() => setEditing(null)}
                >
                  Cancelar
                </button>
              </form>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
