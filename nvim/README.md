# Minimal Neovim Configuration

A modular, minimal Neovim configuration with essential features.

## Features

- Modular structure for easy maintenance
- Mason for LSP installation and management
- LSP features (go to definition, declaration, etc.)
- Diagnostic error window with `<leader>xx`
- Netrw file explorer with useful keymaps
- Tab navigation
- Sensible defaults (relative line numbers, spaces instead of tabs, etc.)

## Directory Structure

```
~/.config/nvim/
├── init.lua            # Main config file
└── lua/
    ├── core/
    │   ├── options.lua    # Basic Vim options
    │   ├── keymaps.lua    # Key mappings
    │   └── autocmds.lua   # Autocommands
    └── plugins/
        ├── init.lua       # Plugin manager setup
        └── configs/
            └── mason.lua  # Mason configuration
```

## Key Mappings

### General

- `<Space>` - Leader key
- `<leader>w` - Save file
- `<leader>q` - Quit
- `<leader>h` - Clear search highlights

### Navigation

- `<C-h/j/k/l>` - Navigate between windows
- `<S-h/l>` - Navigate between buffers
- `L` - Go to next tab
- `<leader>L1-9` - Go to specific tab number

### Netrw File Explorer

- `<leader>e` - Open Netrw in current directory
- `<leader>HS` - Open Netrw in horizontal split
- `<leader>VS` - Open Netrw in vertical split
- `<leader>nt` - Open Netrw in new tab
- `<leader>wl` - Toggle left explorer window

### LSP

- `gD` - Go to declaration
- `gd` - Go to definition (with Telescope UI)
- `K` - Hover documentation
- `gi` - Go to implementation (with Telescope UI)
- `gr` - Find references (with Telescope UI)
- `gt` - Go to type definition (with Telescope UI)
- `<leader>rn` - Rename symbol
- `<leader>ca` - Code actions
- `<leader>f` - Format document

### Telescope

- `<leader>ff` - Find files
- `<leader>fg` - Live grep (search in files)
- `<leader>fb` - Find buffers
- `<leader>fh` - Help tags

### Diagnostics

- `<leader>xx` - Toggle diagnostics window (press again to close)
- `[d` - Go to previous diagnostic
- `]d` - Go to next diagnostic
- `<leader>xd` - Show diagnostic under cursor

## Installing LSPs

1. Open Neovim
2. Run `:Mason`
3. Navigate to the LSP you want to install
4. Press `i` to install it

## Adding New Plugins

Edit `~/.config/nvim/lua/plugins/init.lua` and add your plugins to the table.

## Customization

- To add new options: Edit `~/.config/nvim/lua/core/options.lua`
- To add new keymaps: Edit `~/.config/nvim/lua/core/keymaps.lua`
- To add new autocommands: Edit `~/.config/nvim/lua/core/autocmds.lua`
