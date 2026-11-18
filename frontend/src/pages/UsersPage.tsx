import {
  FormEvent,
  KeyboardEvent,
  ReactNode,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";
import { error } from "../api";
import {
  changeMembershipsBulk,
  createUser,
  getMemberships,
  getProjects,
  getUsers,
  removeMembership,
  resetUserPassword,
  setMembership,
  updateUser,
} from "../lib/users";
import type {
  GlobalRole,
  Membership,
  Project,
  ProjectRole,
  User,
} from "../types";
import "./UsersPage.css";

const PAGE_SIZE = 50;
const emptyCreate = {
  name: "",
  email: "",
  password: "",
  global_role: "user" as GlobalRole,
};
const projectRoles: Record<ProjectRole, string> = {
  manager: "Gestor",
  member: "Membro",
  viewer: "Leitor",
};
type Notice = { kind: "error" | "success"; message: string } | null;
type AccessScope = "none" | "selected" | "all";

function GlobalRoleField({
  value,
  onChange,
}: {
  value: GlobalRole;
  onChange: (value: GlobalRole) => void;
}) {
  const helpId = useId();
  return (
    <label>
      Perfil na ferramenta
      <select
        aria-label="Perfil na ferramenta"
        aria-describedby={helpId}
        value={value}
        onChange={(e) => onChange(e.target.value as GlobalRole)}
      >
        <option value="user">Usuário</option>
        <option value="admin">Administrador da ferramenta</option>
      </select>
      <small id={helpId} className="users-page__field-help">
        Administradores têm acesso global aos projetos atuais e futuros e podem
        gerenciar usuários.
      </small>
    </label>
  );
}

function CreateAccess({
  scope,
  setScope,
  projects,
  selected,
  setSelected,
  role,
  setRole,
  loading,
  failure,
  retry,
}: {
  scope: AccessScope;
  setScope: (scope: AccessScope) => void;
  projects: Project[];
  selected: number[];
  setSelected: (ids: number[]) => void;
  role: ProjectRole;
  setRole: (role: ProjectRole) => void;
  loading: boolean;
  failure: string;
  retry: () => void;
}) {
  const [query, setQuery] = useState("");
  const items = projects.filter((p) =>
    `${p.key} ${p.name}`
      .toLocaleLowerCase()
      .includes(query.trim().toLocaleLowerCase()),
  );
  const needsProjects = scope !== "none";
  return (
    <fieldset className="users-access">
      <legend>Vínculos de projetos</legend>
      <label>
        Projetos iniciais
        <select
          value={scope}
          onChange={(e) => setScope(e.target.value as AccessScope)}
        >
          <option value="none">Nenhum projeto</option>
          <option value="selected">Escolher projetos</option>
          <option value="all">Todos os projetos atuais</option>
        </select>
      </label>
      {needsProjects && loading && (
        <p className="users-access__loading" role="status">
          Carregando projetos…
        </p>
      )}
      {needsProjects && failure && (
        <div className="error" role="alert">
          Não foi possível carregar os projetos. Para cadastrar vínculos,
          recarregue a lista.
          <button type="button" className="quiet" onClick={retry}>
            Recarregar projetos
          </button>
        </div>
      )}
      {needsProjects && !loading && !failure && (
        <>
          <label>
            Papel nos projetos
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as ProjectRole)}
            >
              {Object.entries(projectRoles).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          {scope === "all" ? (
            <p className="users-page__field-help">
              Inclui todos os {projects.length} projetos existentes agora.
              Projetos criados no futuro não serão incluídos.
            </p>
          ) : (
            <>
              <label>
                Buscar projeto
                <input
                  type="search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Nome ou chave"
                />
              </label>
              {!projects.length ? (
                <p className="users-membership__empty">
                  Não há projetos disponíveis para vincular.
                </p>
              ) : (
                <div
                  className="users-project-checklist"
                  aria-label="Projetos selecionados"
                >
                  {items.map((p) => {
                    const checked = selected.includes(p.id);
                    return (
                      <label key={p.id}>
                        <input
                          type="checkbox"
                          aria-label={`Vincular ${p.name}`}
                          checked={checked}
                          onChange={() =>
                            setSelected(
                              checked
                                ? selected.filter((id) => id !== p.id)
                                : [...selected, p.id],
                            )
                          }
                        />
                        <span>
                          <b>{p.key}</b> · {p.name}
                        </span>
                      </label>
                    );
                  })}
                  {!items.length && <p>Nenhum projeto encontrado.</p>}
                </div>
              )}
            </>
          )}
        </>
      )}
    </fieldset>
  );
}

export function UsersPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [q, setQuery] = useState("");
  const [includeInactive, setIncludeInactive] = useState(false);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<Notice>(null);
  const [createForm, setCreateForm] = useState(emptyCreate);
  const [scope, setScope] = useState<AccessScope>("none");
  const [projectRole, setProjectRole] = useState<ProjectRole>("member");
  const [selected, setSelected] = useState<number[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [projectsLoaded, setProjectsLoaded] = useState(false);
  const [projectsFailure, setProjectsFailure] = useState("");
  const [saving, setSaving] = useState(false);
  const [reload, setReload] = useState(0);
  const [editing, setEditing] = useState<User | null>(null);
  const [resetting, setResetting] = useState<User | null>(null);
  const [memberUser, setMemberUser] = useState<User | null>(null);
  const requestId = useRef(0);
  const load = useCallback(async () => {
    const id = ++requestId.current;
    setLoading(true);
    try {
      const page = await getUsers({ q, includeInactive, offset });
      if (id !== requestId.current) return;
      setUsers(page.items);
      setTotal(page.total);
    } catch (reason) {
      if (id === requestId.current)
        setNotice({ kind: "error", message: error(reason) });
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, [includeInactive, offset, q, reload]);
  const loadProjects = useCallback(async () => {
    setProjectsLoading(true);
    setProjectsFailure("");
    try {
      setProjects(await getProjects());
      setProjectsLoaded(true);
    } catch (reason) {
      setProjectsFailure(error(reason));
    } finally {
      setProjectsLoading(false);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    if (
      scope !== "none" &&
      !projectsLoaded &&
      !projectsLoading &&
      !projectsFailure
    )
      void loadProjects();
  }, [scope, projectsLoaded, projectsLoading, projectsFailure, loadProjects]);
  const refresh = () => setReload((value) => value + 1);
  async function submitCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving) return;
    if (scope !== "none" && (projectsLoading || projectsFailure)) {
      setNotice({
        kind: "error",
        message:
          "Aguarde o carregamento dos projetos ou recarregue a lista antes de cadastrar vínculos.",
      });
      return;
    }
    if (scope === "selected" && !selected.length) {
      setNotice({
        kind: "error",
        message: "Selecione ao menos um projeto ou escolha Nenhum projeto.",
      });
      return;
    }
    const fields = new FormData(event.currentTarget);
    setSaving(true);
    setNotice(null);
    try {
      const project_access =
        scope === "none"
          ? undefined
          : {
              scope,
              ...(scope === "selected" ? { project_ids: selected } : {}),
              role: projectRole,
            };
      const created = await createUser({
        name: String(fields.get("name") ?? "").trim(),
        email: String(fields.get("email") ?? "").trim(),
        password: String(fields.get("password") ?? ""),
        global_role: createForm.global_role,
        ...(project_access ? { project_access } : {}),
      });
      setCreateForm(emptyCreate);
      setScope("none");
      setProjectRole("member");
      setSelected([]);
      setNotice({
        kind: "success",
        message:
          scope === "none"
            ? "Conta criada sem vínculos a projetos."
            : "Conta criada com os vínculos de projetos selecionados.",
      });
      setMemberUser(created);
      refresh();
    } catch (reason) {
      setNotice({ kind: "error", message: error(reason) });
    } finally {
      setSaving(false);
    }
  }
  async function saveUser(user: User, data: Parameters<typeof updateUser>[1]) {
    setSaving(true);
    setNotice(null);
    try {
      await updateUser(user.id, data);
      refresh();
      return true;
    } catch (reason) {
      return error(reason);
    } finally {
      setSaving(false);
    }
  }
  async function resetPassword(user: User, password: string) {
    setSaving(true);
    setNotice(null);
    try {
      await resetUserPassword(user.id, password);
      refresh();
      setNotice({
        kind: "success",
        message:
          "Senha redefinida. A pessoa deverá trocá-la no próximo acesso.",
      });
      return true;
    } catch (reason) {
      return error(reason);
    } finally {
      setSaving(false);
    }
  }
  const first = total ? offset + 1 : 0;
  const last = Math.min(offset + users.length, total);
  return (
    <section className="admin-page users-page">
      <div className="hero compact">
        <p className="eyebrow">Administração</p>
        <h1>Usuários</h1>
        <p>
          Cadastre contas, organize seus projetos e controle o acesso global.
        </p>
      </div>
      {notice && (
        <div
          className={`error users-page__notice${notice.kind === "success" ? " users-page__notice--success" : ""}`}
          role={notice.kind === "error" ? "alert" : "status"}
        >
          {notice.message}
          {notice.kind === "error" && (
            <button className="quiet" onClick={refresh}>
              Tentar novamente
            </button>
          )}
        </div>
      )}
      <section className="card">
        <h2>Nova conta</h2>
        <form className="form-grid users-page__form" onSubmit={submitCreate}>
          <label>
            Nome
            <input
              name="name"
              required
              maxLength={200}
              value={createForm.name}
              onChange={(e) =>
                setCreateForm({ ...createForm, name: e.target.value })
              }
            />
          </label>
          <label>
            E-mail
            <input
              name="email"
              required
              type="email"
              maxLength={320}
              value={createForm.email}
              onChange={(e) =>
                setCreateForm({ ...createForm, email: e.target.value })
              }
            />
          </label>
          <label>
            Senha temporária
            <input
              name="password"
              required
              type="password"
              minLength={12}
              autoComplete="new-password"
              value={createForm.password}
              onChange={(e) =>
                setCreateForm({ ...createForm, password: e.target.value })
              }
            />
          </label>
          <GlobalRoleField
            value={createForm.global_role}
            onChange={(global_role) =>
              setCreateForm({ ...createForm, global_role })
            }
          />
          <CreateAccess
            scope={scope}
            setScope={setScope}
            projects={projects}
            selected={selected}
            setSelected={setSelected}
            role={projectRole}
            setRole={setProjectRole}
            loading={projectsLoading}
            failure={projectsFailure}
            retry={() => void loadProjects()}
          />
          <button
            disabled={
              saving ||
              (scope !== "none" &&
                (projectsLoading || Boolean(projectsFailure)))
            }
          >
            {saving ? "Cadastrando…" : "Cadastrar usuário"}
          </button>
        </form>
      </section>
      <section className="card">
        <div className="table-tools users-page__filters">
          <label>
            Buscar
            <input
              type="search"
              value={q}
              onChange={(e) => {
                setQuery(e.target.value);
                setOffset(0);
              }}
              placeholder="Nome ou e-mail"
            />
          </label>
          <label className="users-page__checkbox">
            <input
              type="checkbox"
              checked={includeInactive}
              onChange={(e) => {
                setIncludeInactive(e.target.checked);
                setOffset(0);
              }}
            />{" "}
            Mostrar desativados
          </label>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Pessoa</th>
                <th>Perfil na ferramenta</th>
                <th>Situação</th>
                <th>
                  <span className="sr-only">Ações</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {loading
                ? Array.from({ length: 4 }, (_, i) => (
                    <tr
                      className="users-page__skeleton"
                      key={i}
                      aria-hidden="true"
                    >
                      <td />
                      <td />
                      <td />
                      <td />
                    </tr>
                  ))
                : users.map((user) => (
                    <tr key={user.id}>
                      <td>
                        <b>{user.name}</b>
                        <small>{user.email}</small>
                        {user.must_change_password && (
                          <small>Troca de senha pendente</small>
                        )}
                      </td>
                      <td>
                        <span className="users-page__role">
                          {user.global_role === "admin"
                            ? "Administrador da ferramenta"
                            : "Usuário"}
                        </span>
                      </td>
                      <td>{user.is_active ? "Ativa" : "Desativada"}</td>
                      <td>
                        <div className="users-page__table-actions">
                          <button
                            className="quiet"
                            disabled={saving}
                            onClick={() => setEditing(user)}
                          >
                            Editar
                          </button>
                          <button
                            className="quiet"
                            disabled={saving}
                            onClick={() => setMemberUser(user)}
                          >
                            Projetos e permissões
                          </button>
                          <button
                            className="quiet"
                            disabled={saving}
                            onClick={() =>
                              void saveUser(user, {
                                is_active: !user.is_active,
                              }).then((result) =>
                                setNotice(
                                  result === true
                                    ? {
                                        kind: "success",
                                        message: user.is_active
                                          ? "Conta desativada."
                                          : "Conta reativada. Os vínculos existentes voltam a conceder acesso aos projetos.",
                                      }
                                    : { kind: "error", message: result },
                                ),
                              )
                            }
                          >
                            {user.is_active ? "Desativar" : "Reativar"}
                          </button>
                          <button
                            className="quiet"
                            disabled={saving}
                            onClick={() => setResetting(user)}
                          >
                            Redefinir senha
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
            </tbody>
          </table>
        </div>
        {!loading && !users.length && (
          <div className="empty-state">
            <h2>Nenhuma conta encontrada</h2>
            <p>Ajuste a busca ou cadastre uma nova pessoa.</p>
          </div>
        )}
        <div className="users-page__pagination">
          <p>
            {total ? `Mostrando ${first}–${last} de ${total} usuários` : ""}
          </p>
          <button
            className="quiet"
            disabled={loading || offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            Anterior
          </button>
          <button
            className="quiet"
            disabled={loading || offset + PAGE_SIZE >= total}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Próxima
          </button>
        </div>
      </section>
      {editing && (
        <EditModal
          user={editing}
          saving={saving}
          close={() => setEditing(null)}
          save={(data) => saveUser(editing, data)}
        />
      )}
      {resetting && (
        <PasswordModal
          user={resetting}
          saving={saving}
          close={() => setResetting(null)}
          submit={(password) => resetPassword(resetting, password)}
        />
      )}
      {memberUser && (
        <MembershipModal
          user={memberUser}
          saving={saving}
          close={() => setMemberUser(null)}
          notify={setNotice}
        />
      )}
    </section>
  );
}

function Modal({
  title,
  children,
  close,
  busy = false,
}: {
  title: string;
  children: ReactNode;
  close: () => void;
  busy?: boolean;
}) {
  const dialog = useRef<HTMLElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const focusable = () =>
    Array.from(
      dialog.current?.querySelectorAll<HTMLElement>(
        "button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [href]",
      ) ?? [],
    );
  useEffect(() => {
    opener.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    (focusable()[0] ?? dialog.current)?.focus();
    return () => opener.current?.focus();
  }, []);
  function key(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      if (!busy) close();
      return;
    }
    if (event.key !== "Tab") return;
    const controls = focusable();
    if (!controls.length) {
      event.preventDefault();
      dialog.current?.focus();
      return;
    }
    const first = controls[0],
      last = controls[controls.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }
  return (
    <div
      className="users-modal-backdrop"
      role="presentation"
      onMouseDown={(e) => {
        if (!busy && e.target === e.currentTarget) close();
      }}
    >
      <section
        ref={dialog}
        className="users-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="users-modal-title"
        tabIndex={-1}
        onKeyDown={key}
      >
        <div className="users-modal__heading">
          <h2 id="users-modal-title">{title}</h2>
          <button className="quiet" onClick={close} aria-label="Fechar" disabled={busy}>
            Fechar
          </button>
        </div>
        {children}
      </section>
    </div>
  );
}
function EditModal({
  user,
  saving,
  close,
  save,
}: {
  user: User;
  saving: boolean;
  close: () => void;
  save: (data: Parameters<typeof updateUser>[1]) => Promise<true | string>;
}) {
  const [name, setName] = useState(user.name),
    [email, setEmail] = useState(user.email),
    [role, setRole] = useState(user.global_role),
    [failure, setFailure] = useState("");
  return (
    <Modal title="Editar usuário" close={close}>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setFailure("");
          const result = await save({
            name: name.trim(),
            email: email.trim(),
            global_role: role,
          });
          if (result === true) close();
          else setFailure(result);
        }}
      >
        {failure && (
          <div className="error" role="alert">
            {failure}
          </div>
        )}
        <div className="form-grid">
          <label>
            Nome
            <input
              required
              maxLength={200}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label>
            E-mail
            <input
              required
              type="email"
              maxLength={320}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
        </div>
        <GlobalRoleField value={role} onChange={setRole} />
        <div className="users-modal__buttons">
          <button type="button" className="quiet" onClick={close}>
            Cancelar
          </button>
          <button disabled={saving}>
            {saving ? "Salvando…" : "Salvar alterações"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
function PasswordModal({
  user,
  saving,
  close,
  submit,
}: {
  user: User;
  saving: boolean;
  close: () => void;
  submit: (password: string) => Promise<true | string>;
}) {
  const [failure, setFailure] = useState("");
  return (
    <Modal title="Redefinir senha" close={close}>
      <p>
        Defina uma senha temporária para {user.name}. Ela será trocada no
        próximo acesso.
      </p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setFailure("");
          const result = await submit(
            String(new FormData(e.currentTarget).get("password") ?? ""),
          );
          if (result === true) close();
          else setFailure(result);
        }}
      >
        {failure && (
          <div className="error" role="alert">
            {failure}
          </div>
        )}
        <label>
          Nova senha temporária
          <input
            name="password"
            required
            type="password"
            minLength={12}
            autoComplete="new-password"
          />
        </label>
        <div className="users-modal__buttons">
          <button type="button" className="quiet" onClick={close}>
            Cancelar
          </button>
          <button disabled={saving}>
            {saving ? "Redefinindo…" : "Redefinir senha"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
function MembershipModal({
  user,
  saving,
  close,
  notify,
}: {
  user: User;
  saving: boolean;
  close: () => void;
  notify: (notice: Notice) => void;
}) {
  const [memberships, setMemberships] = useState<Membership[]>([]),
    [projects, setProjects] = useState<Project[]>([]),
    [loading, setLoading] = useState(true),
    [failure, setFailure] = useState(""),
    [projectId, setProjectId] = useState(""),
    [role, setRole] = useState<ProjectRole>("member"),
    [mutating, setMutating] = useState(false),
    [confirmRemove, setConfirmRemove] = useState(false);
  const load = useCallback(async () => {
    setLoading(true);
    setFailure("");
    try {
      const [m, p] = await Promise.all([
        getMemberships(user.id),
        getProjects(),
      ]);
      setMemberships(m);
      setProjects(p);
    } catch (reason) {
      setFailure(error(reason));
    } finally {
      setLoading(false);
    }
  }, [user.id]);
  useEffect(() => {
    void load();
  }, [load]);
  const available = projects.filter(
    (p) => !memberships.some((m) => m.project_id === p.id),
  );
  async function run(action: () => Promise<unknown>, message: string) {
    setMutating(true);
    setFailure("");
    try {
      await action();
      await load();
      notify({ kind: "success", message });
    } catch (reason) {
      setFailure(error(reason));
    } finally {
      setMutating(false);
    }
  }
  return (
    <Modal title="Projetos e permissões" close={close} busy={mutating}>
      <p>
        {user.name} · {user.email}
      </p>
      {user.global_role === "admin" && (
        <p className="users-page__field-help">
          Remover vínculos não revoga o acesso global deste administrador.
        </p>
      )}
      {failure && (
        <div className="error" role="alert">
          {failure}
          <button className="quiet" onClick={() => void load()}>
            Tentar novamente
          </button>
        </div>
      )}
      {loading ? (
        <div
          className="users-memberships users-memberships--skeleton"
          role="status"
        >
          <span />
          <span />
          <span />
        </div>
      ) : (
        <>
          <ul className="users-memberships">
            {memberships.map((m) => (
              <li className="users-membership" key={m.project_id}>
                <span>
                  <b>
                    {m.project_key} · {m.project_name}
                  </b>
                  <small>Permissão no projeto</small>
                </span>
                <select
                  aria-label={`Papel em ${m.project_name}`}
                  value={m.role}
                  disabled={saving || mutating}
                  onChange={(e) =>
                    void run(
                      () =>
                        setMembership(
                          m.project_id,
                          user.email,
                          e.target.value as ProjectRole,
                        ),
                      "Permissão do projeto atualizada.",
                    )
                  }
                >
                  {Object.entries(projectRoles).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
                <button
                  className="quiet"
                  disabled={saving || mutating}
                  onClick={() =>
                    void run(
                      () => removeMembership(m.project_id, user.id),
                      "Vínculo com o projeto removido.",
                    )
                  }
                >
                  Remover
                </button>
              </li>
            ))}
          </ul>
          {!memberships.length && (
            <p className="users-membership__empty">
              Esta pessoa ainda não participa de nenhum projeto.
            </p>
          )}
          <section className="users-bulk-memberships">
            <h3>Todos os projetos atuais</h3>
            <p>
              O papel abaixo será aplicado somente aos novos vínculos. Vínculos
              já existentes são preservados.
            </p>
            <div className="users-bulk-memberships__actions">
              <label>
                Papel para novos vínculos
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value as ProjectRole)}
                  disabled={mutating}
                >
                  {Object.entries(projectRoles).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                disabled={mutating || !available.length}
                onClick={() =>
                  void run(
                    () =>
                      changeMembershipsBulk(user.id, {
                        action: "add",
                        scope: "all",
                        role,
                      }),
                    "Projetos atuais adicionados; vínculos existentes foram preservados.",
                  )
                }
              >
                Adicionar todos os projetos
              </button>
            </div>
            {!available.length && (
              <p className="users-page__field-help">
                Não há novos projetos a adicionar.
              </p>
            )}
            {confirmRemove ? (
              <div className="users-bulk-memberships__confirm" role="alert">
                <b>Remover todos os vínculos?</b>
                <p>
                  {user.name} será removido de {memberships.length}{" "}
                  {memberships.length === 1 ? "projeto" : "projetos"}.{" "}
                  {user.global_role === "admin"
                    ? "O acesso global de administrador continuará ativo."
                    : ""}
                </p>
                <button
                  type="button"
                  disabled={mutating}
                  onClick={() =>
                    void run(
                      () =>
                        changeMembershipsBulk(user.id, {
                          action: "remove",
                          scope: "all",
                        }).then(() => setConfirmRemove(false)),
                      "Todos os vínculos de projetos foram removidos.",
                    )
                  }
                >
                  Confirmar remoção
                </button>
                <button
                  type="button"
                  className="quiet"
                  disabled={mutating}
                  onClick={() => setConfirmRemove(false)}
                >
                  Cancelar
                </button>
              </div>
            ) : (
              <button
                type="button"
                className="quiet"
                disabled={mutating || !memberships.length}
                onClick={() => setConfirmRemove(true)}
              >
                Remover todos os projetos
              </button>
            )}
          </section>
          <form
            className="users-add-membership"
            onSubmit={(e) => {
              e.preventDefault();
              if (projectId)
                void run(
                  () => setMembership(Number(projectId), user.email, role),
                  "Projeto vinculado ao usuário.",
                ).then(() => setProjectId(""));
            }}
          >
            <h3>Adicionar a um projeto</h3>
            <div className="users-add-membership__fields">
              <label>
                Projeto
                <select
                  required
                  value={projectId}
                  onChange={(e) => setProjectId(e.target.value)}
                  disabled={!available.length || mutating}
                >
                  {!available.length ? (
                    <option value="">Sem projetos disponíveis</option>
                  ) : (
                    <>
                      <option value="">Selecione um projeto</option>
                      {available.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.key} · {p.name}
                        </option>
                      ))}
                    </>
                  )}
                </select>
              </label>
              <label>
                Papel
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value as ProjectRole)}
                  disabled={mutating}
                >
                  {Object.entries(projectRoles).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <button disabled={!projectId || mutating}>
                {mutating ? "Salvando…" : "Adicionar"}
              </button>
            </div>
          </form>
        </>
      )}
    </Modal>
  );
}
