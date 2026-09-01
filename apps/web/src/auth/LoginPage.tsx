import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ApiRequestError } from "@guilddesk/api-client";
import { useAuth } from "./AuthContext";
import styles from "./LoginPage.module.css";

type Step = { kind: "credentials" } | { kind: "mfa"; userId: string };

function errorMessage(err: unknown, fallback: string): string {
  return err instanceof ApiRequestError ? err.message : fallback;
}

export function LoginPage() {
  const { login, completeMfaChallenge } = useAuth();
  const navigate = useNavigate();

  const [step, setStep] = useState<Step>({ kind: "credentials" });
  const [orgSlug, setOrgSlug] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleCredentialsSubmit(event: FormEvent): Promise<void> {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const outcome = await login(orgSlug.trim(), email.trim(), password);
      if (outcome.requiresMfa && outcome.mfaChallengeUserId) {
        setStep({ kind: "mfa", userId: outcome.mfaChallengeUserId });
      } else {
        navigate("/", { replace: true });
      }
    } catch (err) {
      setError(errorMessage(err, "Unable to sign in. Please check your details and try again."));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleMfaSubmit(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (step.kind !== "mfa") return;
    setError(null);
    setIsSubmitting(true);
    try {
      await completeMfaChallenge(step.userId, code.trim());
      navigate("/", { replace: true });
    } catch (err) {
      setError(errorMessage(err, "That code didn't work. Please try again."));
    } finally {
      setIsSubmitting(false);
    }
  }

  if (step.kind === "mfa") {
    return (
      <div className={styles.page}>
        <form className={styles.card} onSubmit={handleMfaSubmit}>
          <h1>Verify your identity</h1>
          <p className={styles.hint}>Enter the 6-digit code from your authenticator app.</p>
          <label className={styles.field}>
            Verification code
            <input
              value={code}
              onChange={(event) => setCode(event.target.value)}
              inputMode="numeric"
              autoComplete="one-time-code"
              autoFocus
              required
            />
          </label>
          {error && <p className={styles.error}>{error}</p>}
          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Verifying…" : "Verify"}
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <form className={styles.card} onSubmit={handleCredentialsSubmit}>
        <h1>Sign in to GuildDesk</h1>
        <label className={styles.field}>
          Organization
          <input
            value={orgSlug}
            onChange={(event) => setOrgSlug(event.target.value)}
            placeholder="acme"
            autoComplete="organization"
            required
          />
        </label>
        <p className={styles.hint}>Your organization's slug — ask an admin if you don't know it.</p>
        <label className={styles.field}>
          Email
          <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
        </label>
        <label className={styles.field}>
          Password
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required />
        </label>
        {error && <p className={styles.error}>{error}</p>}
        <button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
