import { FormEvent, useState } from "react";
import { error, login } from "../api";
import type { User } from "../types";
import { publicHref } from "../lib/navigation";

type Props = {
  onLogin: (user: User) => void;
  disabled: boolean;
  logoutError: string;
  retryLogout: () => Promise<void>;
};

export function LoginPage({
  onLogin,
  disabled,
  logoutError,
  retryLogout,
}: Props) {
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || disabled) return;
    // O autofill pode alterar os campos sem emitir eventos para o React.
    const fields = new FormData(event.currentTarget);
    const email = String(fields.get("email") ?? "");
    const password = String(fields.get("password") ?? "");
    setBusy(true);
    setNotice("");
    try {
      onLogin(await login(email, password));
    } catch (failure) {
      setNotice(error(failure));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login">
      <form className="card" onSubmit={submit}>
        <div className="login-brand">
          <strong className="brand-wordmark">J</strong>
        </div>
        <p className="eyebrow">Jornalzinho · espaço do time</p>
        <h1>Seu próximo passo começa aqui.</h1>
        <p>
          Acompanhe as tarefas, converse com o time e veja o que mudou nos
          projetos.
        </p>
        <label>
          E-mail
          <input
            type="email"
            name="email"
            autoComplete="username"
            required
            maxLength={320}
          />
        </label>
        <label>
          Senha
          <input
            type="password"
            name="password"
            autoComplete="current-password"
            required
          />
        </label>
        {notice && (
          <p className="error" role="alert">
            {notice}
          </p>
        )}
        {logoutError && (
          <div className="error" role="alert">
            <p>{logoutError}</p>
            <button
              type="button"
              className="quiet"
              onClick={() => void retryLogout()}
            >
              Tentar sair novamente
            </button>
          </div>
        )}
        <button disabled={busy || disabled}>
          {disabled ? "Encerrando sessão…" : busy ? "Entrando…" : "Entrar"}
        </button>
        <small>
          As contas são cadastradas pela equipe responsável pelo Jornalzinho.
        </small>
        <a href={publicHref("/")}>Voltar ao portal público</a>
      </form>
    </main>
  );
}
