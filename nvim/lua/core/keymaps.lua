-- Core keymaps
local keymap = vim.keymap.set
local opts = { noremap = true, silent = true }

-- Set leader key to space
vim.g.mapleader = " "
vim.g.maplocalleader = " "

-- General keymaps
keymap("n", "<leader>w", ":w<CR>", { desc = "Save file" })
keymap("n", "<leader>q", ":q<CR>", { desc = "Quit" })
keymap("n", "<leader>h", ":nohlsearch<CR>", { desc = "Clear search highlights" })

-- Window navigation
keymap("n", "<C-h>", "<C-w>h", { desc = "Navigate to left window" })
keymap("n", "<C-j>", "<C-w>j", { desc = "Navigate to bottom window" })
keymap("n", "<C-k>", "<C-w>k", { desc = "Navigate to top window" })
keymap("n", "<C-l>", "<C-w>l", { desc = "Navigate to right window" })

-- Resize windows
keymap("n", "<C-Up>", ":resize -2<CR>", opts)
keymap("n", "<C-Down>", ":resize +2<CR>", opts)
keymap("n", "<C-Left>", ":vertical resize -2<CR>", opts)
keymap("n", "<C-Right>", ":vertical resize +2<CR>", opts)

-- Buffers
keymap("n", "<S-l>", ":bnext<CR>", { desc = "Next buffer" })
keymap("n", "<S-h>", ":bprevious<CR>", { desc = "Previous buffer" })
keymap("n", "<leader>c", ":bdelete<CR>", { desc = "Close buffer" })

-- Better indenting
keymap("v", "<", "<gv", opts)
keymap("v", ">", ">gv", opts)

-- Move text up and down
keymap("v", "J", ":m '>+1<CR>gv=gv", opts)
keymap("v", "K", ":m '<-2<CR>gv=gv", opts)

-- Netrw mappings as requested
keymap("n", "<leader>e", ":Explore<CR>", { desc = "Open Netrw in current directory" })
keymap("n", "<leader>HS", ":Hexplore<CR>", { desc = "Open Netrw in horizontal split" })
keymap("n", "<leader>VS", ":Vexplore<CR>", { desc = "Open Netrw in vertical split" })
keymap("n", "<leader>nt", ":Texplore<CR>", { desc = "Open Netrw in new tab" })
keymap("n", "<leader>wl", ":Lexplore<CR>", { desc = "Toggle left explorer window" })

-- Tab navigation
keymap("n", "L", ":tabn<CR>", { desc = "Next tab" })
for i = 1, 9 do
    keymap("n", "<leader>L" .. i, i .. "gt", { desc = "Go to tab " .. i })
end

-- Git keymaps (Global)
keymap("n", "<leader>gg", ":lua require('gitsigns').blame_line{full=true}<CR>", { desc = "Git blame line" })
keymap("n", "<leader>gB", ":lua require('gitsigns').toggle_current_line_blame()<CR>", { desc = "Toggle git blame" })


-- Diagnostics (error window)
-- Toggle diagnostics list for errors and warnings
local diagnostics_active = false
local diagnostics_augroup = vim.api.nvim_create_augroup("custom_diagnostics", { clear = true })

local function toggle_diagnostics()
    if diagnostics_active then
        -- Close the diagnostics float window
        vim.diagnostic.hide()
        vim.cmd("pclose")
        diagnostics_active = false
    else
        -- Open the diagnostics in a new window
        vim.diagnostic.setloclist()
        diagnostics_active = true

        -- Create an autocommand to allow copying to system clipboard from this window
        vim.api.nvim_create_autocmd("FileType", {
            group = diagnostics_augroup,
            pattern = "qf",
            callback = function()
                -- Enable copying to clipboard in the diagnostics window
                vim.opt_local.clipboard = "unnamedplus"

                -- Add a key mapping to close the window
                vim.keymap.set("n", "q", ":pclose<CR>", { buffer = true, noremap = true, silent = true })
            end,
        })
    end
end

keymap("n", "<leader>xx", toggle_diagnostics, { desc = "Toggle diagnostics window" })

-- Additional diagnostic navigation
keymap("n", "[d", vim.diagnostic.goto_prev, { desc = "Go to previous diagnostic" })
keymap("n", "]d", vim.diagnostic.goto_next, { desc = "Go to next diagnostic" })
keymap("n", "<leader>xd", vim.diagnostic.open_float, { desc = "Show diagnostic under cursor" })


-- Move current line/selection down
vim.keymap.set("n", "<A-j>", ":m .+1<CR>==", { noremap = true, silent = true, desc = "Move current line down" })
vim.keymap.set("v", "<A-j>", ":m '>+1<CR>gv=gv", { noremap = true, silent = true, desc = "Move selection down" })

-- Move current line/selection up
vim.keymap.set("n", "<A-k>", ":m .-2<CR>==", { noremap = true, silent = true, desc = "Move current line up" })
vim.keymap.set("v", "<A-k>", ":m '<-2<CR>gv=gv", { noremap = true, silent = true, desc = "Move selection up" })

-- Insert Go error check block
keymap("n", "<leader>qq", function()
  vim.api.nvim_put({
    "if err != nil {",
    '    log.Fatal("some error: ", err)',
    "}",
  }, "l", true, true)
end, { desc = "Insert Go err check" })

