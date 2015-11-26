if !exists('s:is_enabled')
  let s:is_enabled = 0
endif

function! gitsync#init#enable(silent_fail) abort
  if s:is_enabled
    return
  endif

  augroup gitsync
    autocmd!
  augroup END

  if !has('nvim') || !has('python3')
    echomsg '[gitsync] gitsync.nvim requires Neovim with Python3 support ("+python3").'
    return
  endif

  if empty(system('git config --get remote.origin.url'))
    if !a:silent_fail
      echomsg '[gitsync] Not in an upstream-backed git repo. Refusing to load gitsync.nvim'
    endif
    return
  endif

  if !exists(':GitsyncInitPython')
    UpdateRemotePlugins
    echomsg '[gitsync] Please restart Neovim.'
    return
  endif

  GitsyncInitPython

  let s:is_enabled = 1
endfunction
