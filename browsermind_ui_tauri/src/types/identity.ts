export type IdentityStatus = 'active' | 'expired' | 'revoked' | 'requires_2fa';
export type CredentialType = 'password' | 'oauth' | 'apikey' | 'session';

export interface Identity {
  id: string;
  personaId: string;
  environmentKey: string;
  identifier: string;
  status: IdentityStatus;
  credentialType: CredentialType;
  lastUsedAt?: string;
  expiresAt?: string;
  createdAt: string;
}
