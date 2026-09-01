import { useEffect, useState, type FormEvent } from "react";
import { ApiRequestError, type Organization } from "@guilddesk/api-client";
import { useAuth } from "../auth/AuthContext";
import { api } from "../api/apiClient";
import styles from "./SettingsPage.module.css";

type SectionId = "general" | "security";

const SECTIONS: { id: SectionId; label: string }[] = [
  { id: "general", label: "General" },
  { id: "security", label: "Security" },
];

export function SettingsPage() {
  const { user } = useAuth();
  const orgId = user?.org_id;
  const [activeSection, setActiveSection] = useState<SectionId>("general");
  const [organization, setOrganization] = useState<Organization | null>(null);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [description, setDescription] = useState("");
  const [logoUrl, setLogoUrl] = useState("");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (!orgId) return;
    let cancelled = false;
    setIsLoading(true);
    setLoadError(null);

    api.organizations
      .get(orgId)
      .then((org) => {
        if (cancelled) return;
        setOrganization(org);
        setName(org.name);
        setSlug(org.slug);
        setDescription(org.description ?? "");
        setLogoUrl(org.logo_url ?? "");
      })
      .catch((err: unknown) => {
        if (!cancelled) setLoadError(err instanceof ApiRequestError ? err.message : "Failed to load organization.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [orgId]);

  async function handleSubmit(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (!orgId) return;
    setSaveError(null);
    setSaveSuccess(false);
    setIsSaving(true);
    try {
      const updated = await api.organizations.update(orgId, {
        name: name.trim(),
        slug: slug.trim(),
        description,
        logo_url: logoUrl,
      });
      setOrganization(updated);
      setSaveSuccess(true);
    } catch (err) {
      setSaveError(err instanceof ApiRequestError ? err.message : "Failed to save changes.");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div>
      <h1>Organization Settings</h1>
      <div className={styles.layout}>
        <nav className={styles.sectionNav}>
          {SECTIONS.map((section) => (
            <button
              key={section.id}
              type="button"
              className={activeSection === section.id ? styles.sectionActive : styles.section}
              onClick={() => setActiveSection(section.id)}
            >
              {section.label}
            </button>
          ))}
        </nav>
        <div className={styles.content}>
          {loadError && <p className={styles.error}>{loadError}</p>}

          {activeSection === "general" &&
            (isLoading ? (
              <p>Loading…</p>
            ) : (
              organization && (
                <form className={styles.form} onSubmit={handleSubmit}>
                  <label className={styles.field}>
                    Name
                    <input value={name} onChange={(event) => setName(event.target.value)} required />
                  </label>
                  <label className={styles.field}>
                    Slug
                    <input value={slug} onChange={(event) => setSlug(event.target.value)} required />
                  </label>
                  <p className={styles.hint}>Used to sign in — changing it changes what members type at login.</p>
                  <label className={styles.field}>
                    Description
                    <textarea
                      value={description}
                      onChange={(event) => setDescription(event.target.value)}
                      rows={3}
                    />
                  </label>
                  <label className={styles.field}>
                    Logo URL
                    <input
                      type="url"
                      value={logoUrl}
                      onChange={(event) => setLogoUrl(event.target.value)}
                      placeholder="https://…"
                    />
                  </label>
                  <p className={styles.readOnlyRow}>
                    Status: <strong>{organization.status}</strong>
                  </p>
                  {saveError && <p className={styles.error}>{saveError}</p>}
                  {saveSuccess && <p className={styles.success}>Saved.</p>}
                  <button type="submit" disabled={isSaving}>
                    {isSaving ? "Saving…" : "Save changes"}
                  </button>
                </form>
              )
            ))}

          {activeSection === "security" && <p className={styles.comingSoon}>Security settings are coming soon.</p>}
        </div>
      </div>
    </div>
  );
}
