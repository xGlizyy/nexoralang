-- Las cuentas creadas con Google o GitHub no tienen contraseña.
ALTER TABLE users MODIFY password_hash VARCHAR(255) NULL;

-- Identidades externas enlazadas a un usuario. provider_user_id es el id estable del proveedor, no el email.
CREATE TABLE IF NOT EXISTS oauth_accounts (
  provider VARCHAR(20) NOT NULL,
  provider_user_id VARCHAR(64) NOT NULL,
  user_id BIGINT UNSIGNED NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (provider, provider_user_id),
  KEY idx_oauth_accounts_user (user_id),
  CONSTRAINT fk_oauth_accounts_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
