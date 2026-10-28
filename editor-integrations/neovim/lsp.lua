-- NEXORA LSP configuration for Neovim 0.11+.
-- Copy to stdpath("config") .. "/lsp/nexora.lua".
return {
  cmd = { "nexora-lsp" },
  filetypes = { "nexora" },
  root_markers = { ".git" },
  workspace_required = false,
}
