import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { backend, error } from "../api";
import type { Project, ProjectMember, ProjectRole } from "../types";

const roleLabels: Record<ProjectRole, string> = {
  manager: "Gestor",
  member: "Membro",
  viewer: "Leitor",
};

type Notice = { kind: "error" | "success"; message: string } | null;

export function TeamPage({
  project,
  role = "viewer",
}: {
  project: Project;
  role?: ProjectRole | "admin";
}) {
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [email, setEmail] = useState("");
  const [newRole, setNewRole] = useState<ProjectRole>("member");
  const [notice, setNotice] = useState<Notice>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const mounted = useRef(false);
  const requestId = useRef(0);
  const mutationPending = useRef(false);
  const canManage = role === "admin" || role === "manager";
  const allowedRoles: ProjectRole[] =
    role === "admin" ? ["manager", "member", "viewer"] : ["member", "viewer"];

  const load = useCallback(async () => {
    const id = ++requestId.current;
    if (mounted.current) setLoading(true);
    try {
      const data = await backend.allMembers(project.id);
      if (mounted.current && id === requestId.current) setMembers(data);
    } catch (failure) {
      if (mounted.current && id === requestId.current)
        setNotice({ kind: "error", message: error(failure) });
    } finally {
      if (mounted.current && id === requestId.current) setLoading(false);
    }
  }, [project.id]);

  useEffect(() => {
    mounted.current = true;
    void load();
    return () => {
      mounted.current = false;
      requestId.current += 1;
    };
  }, [load]);

  async function runMutation(action: () => Promise<unknown>, success: string) {
    if (mutationPending.current) return;
    mutationPending.current = true;
    setBusy(true);
    setNotice(null);
    try {
      await action();
      if (mounted.current) setNotice({ kind: "success", message: success });
      await load();
      return true;
    } catch (failure) {
      if (mounted.current)
        setNotice({ kind: "error", message: error(failure) });
      return false;
    } finally {
      mutationPending.current = false;
      if (mounted.current) setBusy(false);
    }
  }

  function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canManage) return;
    const trimmedEmail = email.trim();
    if (!trimmedEmail) return;
    void runMutation(
      () => backend.addMember(project.id, trimmedEmail, newRole),
      "Acesso atualizado.",
    ).then((saved) => {
      if (saved && mounted.current) setEmail("");
    });
  }

  function changeRole(member: ProjectMember, nextRole: ProjectRole) {
    if (!canChange(member)) return;
    void runMutation(
      () => backend.addMember(project.id, member.user.email, nextRole),
      "Papel atualizado.",
    );
  }

  function remove(member: ProjectMember) {
    if (!canChange(member)) return;
    void runMutation(
      () => backend.removeMember(project.id, member.user.id),
      "Vínculo removido.",
    );
  }

  function canChange(member: ProjectMember) {
    return canManage && (role === "admin" || member.role !== "manager");
  }

  return (
    <section className="team-page card">
      <p className="eyebrow">{project.key} · equipe</p>
      <h1>Pessoas do projeto</h1>
      {notice && (
        <div
          className={notice.kind === "error" ? "error" : undefined}
          role={notice.kind === "error" ? "alert" : "status"}
        >
          {notice.message}
          {notice.kind === "error" && (
            <button className="quiet" onClick={() => void load()}>
              Tentar novamente
            </button>
          )}
        </div>
      )}
      {canManage ? (
        <form className="form-grid" onSubmit={add}>
          <label>
            E-mail da conta
            <input
              type="email"
              required
              value={email}
              disabled={busy}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <label>
            Papel
            <select
              value={newRole}
              disabled={busy}
              onChange={(event) =>
                setNewRole(event.target.value as ProjectRole)
              }
            >
              {allowedRoles.map((item) => (
                <option key={item} value={item}>
                  {roleLabels[item]}
                </option>
              ))}
            </select>
          </label>
          <button disabled={busy}>
            {busy ? "Salvando…" : "Adicionar à equipe"}
          </button>
        </form>
      ) : (
        <p className="readonly">Você pode consultar a equipe deste projeto.</p>
      )}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Pessoa</th>
              <th>Papel</th>
              <th>Situação</th>
              <th>
                <span className="sr-only">Ações</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {loading
              ? Array.from({ length: 3 }, (_, index) => (
                  <tr key={index} aria-hidden="true">
                    <td>Carregando…</td>
                    <td />
                    <td />
                    <td />
                  </tr>
                ))
              : members.map((member) => {
                  const editable = canChange(member);
                  return (
                    <tr key={member.user.id}>
                      <td>
                        {member.user.name}
                        <small>{member.user.email}</small>
                      </td>
                      <td>
                        {editable ? (
                          <select
                            aria-label={`Papel de ${member.user.name}`}
                            value={member.role}
                            disabled={busy}
                            onChange={(event) =>
                              changeRole(
                                member,
                                event.target.value as ProjectRole,
                              )
                            }
                          >
                            {allowedRoles.map((item) => (
                              <option key={item} value={item}>
                                {roleLabels[item]}
                              </option>
                            ))}
                          </select>
                        ) : (
                          roleLabels[member.role]
                        )}
                      </td>
                      <td>{member.user.is_active ? "Ativa" : "Desativada"}</td>
                      <td>
                        {editable && (
                          <button
                            className="quiet"
                            disabled={busy}
                            onClick={() => remove(member)}
                          >
                            Remover
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
          </tbody>
        </table>
      </div>
      {!loading && !members.length && (
        <div className="empty-state">
          <h2>Nenhuma pessoa vinculada</h2>
          <p>Adicione uma conta para dar acesso a este projeto.</p>
        </div>
      )}
    </section>
  );
}
