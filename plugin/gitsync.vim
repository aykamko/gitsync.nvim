if exists('g:loaded_gitsync')
  finish
endif
let g:loaded_gitsync = 1

command! -nargs=0 -bang -bar GitsyncEnable call gitsync#init#enable(<bang>1)

if get(g:, 'gitsync#enable_at_startup', 1)
  augroup gitsync
    autocmd BufRead * call gitsync#init#enable(1)
  augroup END
endif
