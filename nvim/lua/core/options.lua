-- Core options
local opt = vim.opt

-- Line numbers
opt.number = true         -- Show line numbers
opt.relativenumber = true -- Show relative line numbers

-- Tabs & Indentation
opt.tabstop = 4           -- 4 spaces for tabs
opt.shiftwidth = 4        -- 4 spaces for indent width
opt.expandtab = true      -- Use spaces instead of tabs
opt.autoindent = true     -- Copy indent from current line when starting new one
opt.smartindent = true    -- Smart autoindent when starting a new line

-- Search
opt.ignorecase = true     -- Ignore case when searching
opt.smartcase = true      -- Don't ignore case with capitals
opt.hlsearch = true       -- Highlight search matches
opt.incsearch = true      -- Show search matches as you type

-- Appearance
opt.termguicolors = true  -- Enable 24-bit RGB colors
opt.signcolumn = "yes"    -- Always show the signcolumn
opt.cursorline = true     -- Highlight the current line
opt.scrolloff = 8         -- Min number of lines to keep above and below cursor
opt.sidescrolloff = 8     -- Min number of columns to keep left and right of cursor

-- Behavior
opt.hidden = true         -- Allow switching from unsaved buffers
opt.splitbelow = true     -- Put new horizontal splits below
opt.splitright = true     -- Put new vertical splits to the right
opt.wrap = false          -- Don't wrap lines
opt.backup = false        -- Don't create backup files
opt.swapfile = false      -- Don't create swap files
opt.undofile = true       -- Enable persistent undo

-- Performance
opt.updatetime = 300      -- Faster completion
opt.timeoutlen = 500      -- Time to wait for a mapped sequence to complete (in milliseconds)

-- Clipboard
opt.clipboard = "unnamedplus" -- Use system clipboard
