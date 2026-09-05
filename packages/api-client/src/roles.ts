import type { ApiClient } from "./client";
import type { DataResponse } from "./types";

// Mirrors app.identity.presentation.schemas — RoleResponse, PermissionResponse,
// PermissionMatrixResponse, AssignRoleRequest.

export interface Permission {
  id: string;
  resource: string;
  action: string;
  description: string;
}

export interface Role {
  id: string;
  org_id: string | null;
  name: string;
  description: string;
  is_system_role: boolean;
  parent_role_id: string | null;
  permission_ids: string[];
}

export interface PermissionMatrix {
  permissions: Permission[];
  roles: Role[];
}

export function createRolesApi(client: ApiClient) {
  return {
    async listForOrg(orgId: string): Promise<Role[]> {
      const response = await client.get<DataResponse<Role[]>>(`/api/v1/organizations/${orgId}/roles`);
      return response.data;
    },

    async listForMember(orgId: string, userId: string): Promise<Role[]> {
      const response = await client.get<DataResponse<Role[]>>(
        `/api/v1/organizations/${orgId}/members/${userId}/roles`,
      );
      return response.data;
    },

    async getPermissionMatrix(orgId: string): Promise<PermissionMatrix> {
      const response = await client.get<DataResponse<PermissionMatrix>>(
        `/api/v1/organizations/${orgId}/permission-matrix`,
      );
      return response.data;
    },

    async create(name: string, description = ""): Promise<Role> {
      const response = await client.post<DataResponse<Role>>("/api/v1/roles", { name, description });
      return response.data;
    },

    async update(roleId: string, name: string): Promise<Role> {
      const response = await client.patch<DataResponse<Role>>(`/api/v1/roles/${roleId}`, { name });
      return response.data;
    },

    async delete(roleId: string): Promise<void> {
      await client.delete<void>(`/api/v1/roles/${roleId}`);
    },

    async grantPermission(roleId: string, permissionId: string): Promise<Role> {
      const response = await client.post<DataResponse<Role>>(`/api/v1/roles/${roleId}/permissions`, {
        permission_id: permissionId,
      });
      return response.data;
    },

    async revokePermission(roleId: string, permissionId: string): Promise<Role> {
      const response = await client.delete<DataResponse<Role>>(
        `/api/v1/roles/${roleId}/permissions/${permissionId}`,
      );
      return response.data;
    },

    async assignToUser(userId: string, roleId: string): Promise<void> {
      await client.post<void>("/api/v1/roles/assign", { user_id: userId, role_id: roleId });
    },

    async revokeFromUser(userId: string, roleId: string): Promise<void> {
      await client.post<void>("/api/v1/roles/revoke", { user_id: userId, role_id: roleId });
    },
  };
}
