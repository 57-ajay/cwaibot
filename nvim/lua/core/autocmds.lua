-- Autocommands
local augroup = vim.api.nvim_create_augroup
local autocmd = vim.api.nvim_create_autocmd

-- General autocommands
local general = augroup("General", { clear = true })

-- Highlight on yank
autocmd("TextYankPost", {
    group = general,
    callback = function()
        vim.highlight.on_yank({ higroup = "IncSearch", timeout = 150 })
    end,
})

-- Auto-format on save (if LSP provides formatting)
autocmd("BufWritePre", {
    group = general,
    callback = function()
        vim.lsp.buf.format({ async = false })
    end,
})

-- Remove trailing whitespace on save
autocmd("BufWritePre", {
    group = general,
    pattern = "*",
    command = [[%s/\s\+$//e]],
})

-- Return to last edit position when opening files
autocmd("BufReadPost", {
    group = general,
    callback = function()
        local mark = vim.api.nvim_buf_get_mark(0, '"')
        local line_count = vim.api.nvim_buf_line_count(0)
        if mark[1] > 0 and mark[1] <= line_count then
            vim.api.nvim_win_set_cursor(0, mark)
        end
    end,
})

-- Configure Netrw
vim.g.netrw_banner = 0       -- Hide banner
vim.g.netrw_liststyle = 3    -- Tree view
vim.g.netrw_browse_split = 0 -- Open in current window by default
