import { FormEvent, useState } from "react";
import { backend, error, logout } from "../api";
import type { User } from "../types";

export function AccountPage({
  user,
  required,
  done,
}: {
  user: User;
  required?: boolean;
  done: () => void;
}) {
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    // Leia o formulário: o autofill pode não emitir eventos de alteração.
    const fields = new FormData(e.currentTarget);
    const current = String(fields.get("current_password") ?? "");
    const next = String(fields.get("new_password") ?? "");
    if (!current) {
      setNotice("Informe sua senha atual.");
      return;
    }
    if (!next) {
      setNotice("Informe a nova senha.");
      return;
    }
    if (current === next) {
      setNotice("Informe uma nova senha diferente da atual.");
      return;
    }
    setBusy(true);
    setNotice("");
    try {
      await backend.changePassword(current, next);
      done();
      try {
        await logout();
      } catch {
        // A senha já revogou as sessões no servidor; a interface permanece limpa.
      }
    } catch (failure) {
      setNotice(error(failure));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="account-page card">
      <p className="eyebrow">Conta</p>
      <h1>
        {required ? "Troque sua senha para continuar" : "Segurança da conta"}
      </h1>
      <p>
        {required
          ? "Informe sua senha temporária no campo Senha atual e escolha uma nova senha."
          : `Você está conectado como ${user.email}.`}
      </p>
      <form onSubmit={submit}>
        <label>
          Senha atual
          <input
            type="password"
            autoComplete="current-password"
            name="current_password"
            required
          />
        </label>
        <label>
          Nova senha
          <input
            type="password"
            autoComplete="new-password"
            minLength={12}
            name="new_password"
            required
          />
        </label>
        {notice && (
          <p className="error" role="alert">
            {notice}
          </p>
        )}
        <button disabled={busy}>
          {busy ? "Atualizando…" : "Trocar senha"}
        </button>
      </form>
    </section>
  );
}
