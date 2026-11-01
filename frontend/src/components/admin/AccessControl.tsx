import { Plus, Save, Trash2, UserMinus, UserPlus } from 'lucide-react';
import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  useAdminGroups,
  useAdminPermissions,
  useAdminRoles,
  useAdminUsers,
  useGroupMember,
  useSaveGroup,
  useSaveRole,
  type AccessGroup,
  type AccessRole,
} from '@/api/auth';
import { ApiRequestError } from '@/api/client';
import { StatePanel } from '@/components/common/StatePanel';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

/**
 * Custom roles and groups for administrators (migration 0026). The server decides every
 * permission: these panels only edit what it stores, and it refuses what is not allowed
 * (built-in roles stay fixed; the administrator role is never given through a group).
 */

/** The permission's name in the page language; the server's description otherwise. */
export function usePermissionLabel(): (code: string, fallback?: string) => string {
  const { t, i18n } = useTranslation();
  return (code, fallback) => {
    const key = `access.permission.${code.replace(/\./g, '_')}`;
    return i18n.exists(key) ? t(key as 'access.title') : fallback ?? code;
  };
}

export function useRoleLabel(): (code: string) => string {
  const { t, i18n } = useTranslation();
  return (code) => {
    const key = `account.role.${code}`;
    return i18n.exists(key) ? t(key as 'access.title') : code;
  };
}

function ErrorLine({ error }: { error: unknown }) {
  const { t, i18n } = useTranslation();
  if (!error) return null;
  const code = error instanceof ApiRequestError ? error.code : '';
  const key = `access.errors.${code}`;
  const text = code && i18n.exists(key) ? t(key as 'access.title') : error instanceof Error ? error.message : t('access.errors.other');
  return <p role="alert" className="text-sm text-destructive">{text}</p>;
}

function PermissionChecks({ value, onChange, idPrefix }: { value: string[]; onChange: (next: string[]) => void; idPrefix: string }) {
  const { t } = useTranslation();
  const permissions = useAdminPermissions(true);
  const label = usePermissionLabel();
  if (!permissions.data) return null;
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 text-sm font-medium">{t('access.permissions')}</legend>
      <div className="grid gap-1.5 sm:grid-cols-2">
        {permissions.data.map((p) => (
          <label key={p.code} htmlFor={`${idPrefix}-${p.code}`} className="flex items-start gap-2 text-sm">
            <input id={`${idPrefix}-${p.code}`} type="checkbox" className="mt-1 size-4 accent-primary" checked={value.includes(p.code)}
              onChange={(e) => onChange(e.target.checked ? [...value, p.code] : value.filter((c) => c !== p.code))}
              data-testid={`permission-${p.code}`} />
            <span>{label(p.code, p.description)} <span className="font-mono text-xs text-muted-foreground" dir="ltr">{p.code}</span></span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

// ------------------------------------------------------------------ roles

export function RolesPanel() {
  const { t } = useTranslation();
  const roles = useAdminRoles(true);
  const roleLabel = useRoleLabel();
  const permLabel = usePermissionLabel();
  const [editing, setEditing] = useState<AccessRole | 'new' | null>(null);

  if (roles.isPending) return <StatePanel kind="loading" skeleton="lines" />;
  if (roles.isError) return <StatePanel kind="error" detail={roles.error.message} onRetry={() => void roles.refetch()} />;
  return (
    <section className="flex flex-col gap-4" data-testid="roles-panel">
      <p className="text-base text-muted-foreground">{t('access.rolesIntro')}</p>
      <ul className="grid gap-3 lg:grid-cols-2">
        {roles.data.map((r) => (
          <li key={r.code} className="surface-card flex flex-col gap-2 p-4" data-testid="role-card" data-role={r.code}>
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-base font-semibold">{roleLabel(r.code)}</h3>
              <Badge variant={r.builtin ? 'verified' : 'sand'}>{r.builtin ? t('access.builtin') : t('access.custom')}</Badge>
              <span className="text-sm text-muted-foreground">{t('access.usage', { users: r.users, groups: r.groups })}</span>
            </div>
            <p className="text-sm text-muted-foreground">{r.description}</p>
            <p className="text-sm">{r.permissions.length ? r.permissions.map((p) => permLabel(p)).join(' · ') : t('access.noPermissions')}</p>
            {r.builtin ? null : (
              <Button variant="outline" size="sm" className="w-fit" onClick={() => setEditing(r)} data-testid="role-edit">{t('access.edit')}</Button>
            )}
          </li>
        ))}
      </ul>
      {editing ? (
        <RoleEditor key={editing === 'new' ? 'new' : editing.code} role={editing === 'new' ? null : editing} onDone={() => setEditing(null)} />
      ) : (
        <Button className="w-fit" onClick={() => setEditing('new')} data-testid="role-new"><Plus aria-hidden="true" />{t('access.newRole')}</Button>
      )}
    </section>
  );
}

function RoleEditor({ role, onDone }: { role: AccessRole | null; onDone: () => void }) {
  const { t } = useTranslation();
  const save = useSaveRole();
  const id = useId();
  const [code, setCode] = useState(role?.code ?? '');
  const [description, setDescription] = useState(role?.description ?? '');
  const [permissions, setPermissions] = useState<string[]>(role?.permissions ?? []);
  const submit = (mode: 'create' | 'update' | 'delete') =>
    save.mutate({ code, description, permissions, mode }, { onSuccess: onDone });
  return (
    <form className="surface-card flex flex-col gap-4 p-5" data-testid="role-editor" noValidate
      onSubmit={(e) => { e.preventDefault(); submit(role ? 'update' : 'create'); }}>
      <h3 className="text-lg font-semibold">{role ? t('access.editRole') : t('access.newRole')}</h3>
      <div className="flex flex-col gap-1.5">
        <label htmlFor={`${id}-code`} className="text-sm font-medium">{t('access.roleCode')}</label>
        <input id={`${id}-code`} value={code} onChange={(e) => setCode(e.target.value)} disabled={Boolean(role)} dir="ltr"
          className="h-10 rounded-md border border-border-strong bg-card px-3 font-mono text-sm" data-testid="role-code" />
        <p className="text-sm text-muted-foreground">{t('access.roleCodeHint')}</p>
      </div>
      <div className="flex flex-col gap-1.5">
        <label htmlFor={`${id}-description`} className="text-sm font-medium">{t('access.description')}</label>
        <input id={`${id}-description`} value={description} onChange={(e) => setDescription(e.target.value)} maxLength={300}
          className="h-10 rounded-md border border-border-strong bg-card px-3 text-base" data-testid="role-description" />
      </div>
      <PermissionChecks value={permissions} onChange={setPermissions} idPrefix={`${id}-perm`} />
      <ErrorLine error={save.error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={save.isPending || !code || !description} data-testid="role-save"><Save aria-hidden="true" />{t('access.save')}</Button>
        <Button type="button" variant="ghost" onClick={onDone}>{t('access.cancel')}</Button>
        {role ? (
          <Button type="button" variant="outline" className="ms-auto" disabled={save.isPending} onClick={() => submit('delete')} data-testid="role-delete">
            <Trash2 aria-hidden="true" />{t('access.deleteRole')}
          </Button>
        ) : null}
      </div>
    </form>
  );
}

// ------------------------------------------------------------------ groups

export function GroupsPanel() {
  const { t } = useTranslation();
  const groups = useAdminGroups(true);
  const [editing, setEditing] = useState<AccessGroup | 'new' | null>(null);
  if (groups.isPending) return <StatePanel kind="loading" skeleton="lines" />;
  if (groups.isError) return <StatePanel kind="error" detail={groups.error.message} onRetry={() => void groups.refetch()} />;
  return (
    <section className="flex flex-col gap-4" data-testid="groups-panel">
      <p className="text-base text-muted-foreground">{t('access.groupsIntro')}</p>
      {groups.data.length === 0 ? <p className="text-base text-muted-foreground">{t('access.noGroups')}</p> : (
        <ul className="grid gap-3 lg:grid-cols-2">
          {groups.data.map((g) => <GroupCard key={g.id} group={g} onEdit={() => setEditing(g)} />)}
        </ul>
      )}
      {editing ? (
        <GroupEditor key={editing === 'new' ? 'new' : editing.id} group={editing === 'new' ? null : editing} onDone={() => setEditing(null)} />
      ) : (
        <Button className="w-fit" onClick={() => setEditing('new')} data-testid="group-new"><Plus aria-hidden="true" />{t('access.newGroup')}</Button>
      )}
    </section>
  );
}

function GroupCard({ group, onEdit }: { group: AccessGroup; onEdit: () => void }) {
  const { t } = useTranslation();
  const users = useAdminUsers(true);
  const member = useGroupMember();
  const roleLabel = useRoleLabel();
  const permLabel = usePermissionLabel();
  const [adding, setAdding] = useState('');
  const memberIds = new Set(group.members.map((m) => m.id));
  const candidates = (users.data ?? []).filter((u) => !memberIds.has(u.id));
  return (
    <li className="surface-card flex flex-col gap-3 p-4" data-testid="group-card" data-group={group.name}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-base font-semibold">{group.name}</h3>
        <span className="text-sm text-muted-foreground">{t('access.members', { count: group.members.length })}</span>
      </div>
      {group.description ? <p className="text-sm text-muted-foreground">{group.description}</p> : null}
      <p className="text-sm"><span className="font-medium">{t('access.roles')}: </span>{group.roles.map(roleLabel).join(' · ') || '—'}</p>
      <p className="text-sm"><span className="font-medium">{t('access.permissions')}: </span>{group.permissions.map((p) => permLabel(p)).join(' · ') || '—'}</p>
      <ul className="flex flex-col gap-1" data-testid="group-members">
        {group.members.map((m) => (
          <li key={m.id} className="flex items-center justify-between gap-2 text-sm">
            <span>{m.display_name} <span className="text-muted-foreground" dir="ltr">{m.username ? `@${m.username}` : m.email ?? ''}</span></span>
            <Button variant="ghost" size="sm" aria-label={t('access.removeMember', { name: m.display_name })}
              onClick={() => member.mutate({ groupId: group.id, userId: m.id, add: false })}><UserMinus aria-hidden="true" /></Button>
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap items-center gap-2">
        <select aria-label={t('access.addMember')} value={adding} onChange={(e) => setAdding(e.target.value)}
          className="h-9 min-w-0 flex-1 rounded-md border border-border-strong bg-card px-2 text-sm" data-testid="group-add-select">
          <option value="">{t('access.chooseUser')}</option>
          {candidates.map((u) => <option key={u.id} value={u.id}>{u.display_name}{u.username ? ` (@${u.username})` : u.email ? ` (${u.email})` : ''}</option>)}
        </select>
        <Button variant="outline" size="sm" disabled={!adding || member.isPending} data-testid="group-add"
          onClick={() => member.mutate({ groupId: group.id, userId: adding, add: true }, { onSuccess: () => setAdding('') })}>
          <UserPlus aria-hidden="true" />{t('access.addMember')}
        </Button>
        <Button variant="ghost" size="sm" onClick={onEdit} data-testid="group-edit">{t('access.edit')}</Button>
      </div>
      <ErrorLine error={member.error} />
    </li>
  );
}

function GroupEditor({ group, onDone }: { group: AccessGroup | null; onDone: () => void }) {
  const { t } = useTranslation();
  const save = useSaveGroup();
  const roles = useAdminRoles(true);
  const roleLabel = useRoleLabel();
  const id = useId();
  const [name, setName] = useState(group?.name ?? '');
  const [description, setDescription] = useState(group?.description ?? '');
  const [roleCodes, setRoleCodes] = useState<string[]>(group?.roles ?? []);
  const [permissions, setPermissions] = useState<string[]>(group?.permissions ?? []);
  const submit = (mode: 'create' | 'update' | 'delete') =>
    save.mutate({ id: group?.id, name, description, roles: roleCodes, permissions, mode }, { onSuccess: onDone });
  return (
    <form className="surface-card flex flex-col gap-4 p-5" data-testid="group-editor" noValidate
      onSubmit={(e) => { e.preventDefault(); submit(group ? 'update' : 'create'); }}>
      <h3 className="text-lg font-semibold">{group ? t('access.editGroup') : t('access.newGroup')}</h3>
      <div className="flex flex-col gap-1.5">
        <label htmlFor={`${id}-name`} className="text-sm font-medium">{t('access.groupName')}</label>
        <input id={`${id}-name`} value={name} onChange={(e) => setName(e.target.value)} maxLength={80}
          className="h-10 rounded-md border border-border-strong bg-card px-3 text-base" data-testid="group-name" />
      </div>
      <div className="flex flex-col gap-1.5">
        <label htmlFor={`${id}-description`} className="text-sm font-medium">{t('access.description')}</label>
        <input id={`${id}-description`} value={description} onChange={(e) => setDescription(e.target.value)} maxLength={500}
          className="h-10 rounded-md border border-border-strong bg-card px-3 text-base" />
      </div>
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-sm font-medium">{t('access.roles')}</legend>
        <p className="text-sm text-muted-foreground">{t('access.noAdminByGroup')}</p>
        <div className="flex flex-wrap gap-3">
          {(roles.data ?? []).filter((r) => r.code !== 'administrator').map((r) => (
            <label key={r.code} className="flex items-center gap-2 text-sm">
              <input type="checkbox" className="size-4 accent-primary" checked={roleCodes.includes(r.code)} data-testid={`group-role-${r.code}`}
                onChange={(e) => setRoleCodes(e.target.checked ? [...roleCodes, r.code] : roleCodes.filter((c) => c !== r.code))} />
              {roleLabel(r.code)}
            </label>
          ))}
        </div>
      </fieldset>
      <PermissionChecks value={permissions} onChange={setPermissions} idPrefix={`${id}-perm`} />
      <ErrorLine error={save.error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={save.isPending || !name.trim()} data-testid="group-save"><Save aria-hidden="true" />{t('access.save')}</Button>
        <Button type="button" variant="ghost" onClick={onDone}>{t('access.cancel')}</Button>
        {group ? (
          <Button type="button" variant="outline" className="ms-auto" disabled={save.isPending} onClick={() => submit('delete')} data-testid="group-delete">
            <Trash2 aria-hidden="true" />{t('access.deleteGroup')}
          </Button>
        ) : null}
      </div>
    </form>
  );
}
