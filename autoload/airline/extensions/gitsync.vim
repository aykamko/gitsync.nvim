if !get(g:, 'gitsync_airline', 1)
    finish
endif

let s:spc = g:airline_symbols.space

function! airline#extensions#gitsync#apply(...)
    let w:airline_section_warning = get(w:, 'airline_section_warning', g:airline_section_warning)
    let w:airline_section_warning .= s:spc.'%{GitsyncStatus()}'
endfunction

function! airline#extensions#gitsync#init(ext)
    call airline#parts#define_function('gitsync', 'GitsyncStatus')
    call a:ext.add_statusline_func('airline#extensions#gitsync#apply')
endfunction
