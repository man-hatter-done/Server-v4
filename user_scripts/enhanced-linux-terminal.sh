#!/bin/bash
# Real Linux Terminal Environment Setup
# This script enhances the existing terminal environment with real Linux functionality

# Define colors for better output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}Setting up Real Linux Terminal Environment...${NC}"

# Create necessary directories
mkdir -p "$HOME/.local/bin"
mkdir -p "$HOME/.local/lib"
mkdir -p "$HOME/.config"
mkdir -p "$HOME/.cache"

# Setup bash configuration
if [ -f "$HOME/.bashrc" ]; then
    # Check if our enhancements are already added
    if ! grep -q "Real Linux Terminal" "$HOME/.bashrc"; then
        echo -e "${YELLOW}Enhancing bash configuration...${NC}"
        cat >> "$HOME/.bashrc" << 'BASHRC'

# Real Linux Terminal Environment
export PATH="$HOME/.local/bin:$HOME/bin:$PATH"

# More colorful and informative prompt
PS1='\[\033[01;32m\]\u@\h\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]$([ $? -eq 0 ] && echo -e "\[\033[01;32m\] ✓" || echo -e "\[\033[01;31m\] ✗ $?")\[\033[00m\]\$ '

# Enable color support
if [ -x /usr/bin/dircolors ]; then
    test -r ~/.dircolors && eval "$(dircolors -b ~/.dircolors)" || eval "$(dircolors -b)"
    alias ls='ls --color=auto'
    alias dir='dir --color=auto'
    alias vdir='vdir --color=auto'
    alias grep='grep --color=auto'
    alias fgrep='fgrep --color=auto'
    alias egrep='egrep --color=auto'
    alias diff='diff --color=auto'
fi

# Useful aliases
alias ll='ls -la'
alias la='ls -A'
alias l='ls -CF'
alias cls='clear'
alias h='history'
alias ..='cd ..'
alias ...='cd ../..'
alias mkdir='mkdir -p'
alias df='df -h'
alias du='du -h'
alias free='free -h'

# Enhanced history
export HISTSIZE=10000
export HISTFILESIZE=20000
export HISTCONTROL=ignoreboth:erasedups
export HISTTIMEFORMAT="%F %T "
shopt -s histappend

# Better tab completion
if [ -f /etc/bash_completion ] && ! shopt -oq posix; then
    . /etc/bash_completion
fi

# Better directory navigation
shopt -s autocd
shopt -s dirspell
shopt -s cdspell

# Useful functions
mkcd() {
    mkdir -p "$1" && cd "$1"
}

extract() {
    if [ -f "$1" ]; then
        case "$1" in
            *.tar.bz2)   tar xjf "$1"     ;;
            *.tar.gz)    tar xzf "$1"     ;;
            *.bz2)       bunzip2 "$1"     ;;
            *.rar)       unrar e "$1"     ;;
            *.gz)        gunzip "$1"      ;;
            *.tar)       tar xf "$1"      ;;
            *.tbz2)      tar xjf "$1"     ;;
            *.tgz)       tar xzf "$1"     ;;
            *.zip)       unzip "$1"       ;;
            *.Z)         uncompress "$1"  ;;
            *.7z)        7z x "$1"        ;;
            *)           echo "'$1' cannot be extracted via extract" ;;
        esac
    else
        echo "'$1' is not a valid file"
    fi
}

# Set default editor
if command -v vim > /dev/null 2>&1; then
    export EDITOR='vim'
    export VISUAL='vim'
elif command -v nano > /dev/null 2>&1; then
    export EDITOR='nano'
    export VISUAL='nano'
fi
BASHRC
    fi
else
    # Create new .bashrc
    echo -e "${YELLOW}Creating new bash configuration...${NC}"
    cat > "$HOME/.bashrc" << 'BASHRC'
# .bashrc - Bash initialization file

# If not running interactively, don't do anything
case $- in
    *i*) ;;
      *) return;;
esac

# Real Linux Terminal Environment
export PATH="$HOME/.local/bin:$HOME/bin:$PATH"

# More colorful and informative prompt
PS1='\[\033[01;32m\]\u@\h\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]$([ $? -eq 0 ] && echo -e "\[\033[01;32m\] ✓" || echo -e "\[\033[01;31m\] ✗ $?")\[\033[00m\]\$ '

# Enable color support
if [ -x /usr/bin/dircolors ]; then
    test -r ~/.dircolors && eval "$(dircolors -b ~/.dircolors)" || eval "$(dircolors -b)"
    alias ls='ls --color=auto'
    alias dir='dir --color=auto'
    alias vdir='vdir --color=auto'
    alias grep='grep --color=auto'
    alias fgrep='fgrep --color=auto'
    alias egrep='egrep --color=auto'
    alias diff='diff --color=auto'
fi

# Useful aliases
alias ll='ls -la'
alias la='ls -A'
alias l='ls -CF'
alias cls='clear'
alias h='history'
alias ..='cd ..'
alias ...='cd ../..'
alias mkdir='mkdir -p'
alias df='df -h'
alias du='du -h'
alias free='free -h'

# Enhanced history
export HISTSIZE=10000
export HISTFILESIZE=20000
export HISTCONTROL=ignoreboth:erasedups
export HISTTIMEFORMAT="%F %T "
shopt -s histappend

# Better tab completion
if [ -f /etc/bash_completion ] && ! shopt -oq posix; then
    . /etc/bash_completion
fi

# Better directory navigation
shopt -s autocd
shopt -s dirspell
shopt -s cdspell

# Useful functions
mkcd() {
    mkdir -p "$1" && cd "$1"
}

extract() {
    if [ -f "$1" ]; then
        case "$1" in
            *.tar.bz2)   tar xjf "$1"     ;;
            *.tar.gz)    tar xzf "$1"     ;;
            *.bz2)       bunzip2 "$1"     ;;
            *.rar)       unrar e "$1"     ;;
            *.gz)        gunzip "$1"      ;;
            *.tar)       tar xf "$1"      ;;
            *.tbz2)      tar xjf "$1"     ;;
            *.tgz)       tar xzf "$1"     ;;
            *.zip)       unzip "$1"       ;;
            *.Z)         uncompress "$1"  ;;
            *.7z)        7z x "$1"        ;;
            *)           echo "'$1' cannot be extracted via extract" ;;
        esac
    else
        echo "'$1' is not a valid file"
    fi
}

# Set default editor
if command -v vim > /dev/null 2>&1; then
    export EDITOR='vim'
    export VISUAL='vim'
elif command -v nano > /dev/null 2>&1; then
    export EDITOR='nano'
    export VISUAL='nano'
fi
BASHRC
fi

# Setup .profile if it doesn't exist or update it
if [ -f "$HOME/.profile" ]; then
    if ! grep -q "Real Linux Terminal" "$HOME/.profile"; then
        echo -e "${YELLOW}Enhancing profile configuration...${NC}"
        cat >> "$HOME/.profile" << 'PROFILE'

# Real Linux Terminal Environment
if [ -n "$BASH_VERSION" ]; then
    if [ -f "$HOME/.bashrc" ]; then
        . "$HOME/.bashrc"
    fi
fi

# Set PATH so it includes user's private bin if it exists
if [ -d "$HOME/.local/bin" ] ; then
    PATH="$HOME/.local/bin:$PATH"
fi
if [ -d "$HOME/bin" ] ; then
    PATH="$HOME/bin:$PATH"
fi

# Set environment variables
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
export TERM=xterm-256color
PROFILE
    fi
else
    echo -e "${YELLOW}Creating profile configuration...${NC}"
    cat > "$HOME/.profile" << 'PROFILE'
# ~/.profile: executed by the command interpreter for login shells

# Real Linux Terminal Environment
if [ -n "$BASH_VERSION" ]; then
    if [ -f "$HOME/.bashrc" ]; then
        . "$HOME/.bashrc"
    fi
fi

# Set PATH so it includes user's private bin if it exists
if [ -d "$HOME/.local/bin" ] ; then
    PATH="$HOME/.local/bin:$PATH"
fi
if [ -d "$HOME/bin" ] ; then
    PATH="$HOME/bin:$PATH"
fi

# Set environment variables
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
export TERM=xterm-256color
PROFILE
fi

# Set up vim configuration if available
if command -v vim > /dev/null 2>&1; then
    echo -e "${YELLOW}Setting up vim configuration...${NC}"
    cat > "$HOME/.vimrc" << 'VIMRC'
" Basic Settings
syntax on                 " Enable syntax highlighting
set number                " Show line numbers
set relativenumber        " Relative line numbers
set tabstop=4             " Tab width
set softtabstop=4         " Tab width while editing
set shiftwidth=4          " Indentation width
set expandtab             " Use spaces instead of tabs
set smarttab              " Smart tab handling
set autoindent            " Auto indent
set smartindent           " Smart indent
set wrap                  " Wrap lines
set linebreak             " Break lines at word boundaries
set showmatch             " Show matching brackets
set hlsearch              " Highlight search results
set incsearch             " Incremental search
set ignorecase            " Ignore case when searching
set smartcase             " Override ignorecase when uppercase is used
set ruler                 " Show cursor position
set showcmd               " Show command in bottom bar
set wildmenu              " Visual autocomplete for command menu
set laststatus=2          " Always show status line
set statusline=%f\ %h%w%m%r\ %=%(%l,%c%V\ %=\ %P%)
set mouse=a               " Enable mouse usage
set backspace=indent,eol,start  " Make backspace work properly
set history=1000          " Command history
set undolevels=1000       " Undo history
set wildmode=longest,list,full  " Command completion
set wildmenu              " Command completion menu
set wildignore=*.o,*~,*.pyc  " Ignore compiled files
set title                 " Set termina^
S save main
bind 
^
Q exit main
bind 
^
W writeout main
bind 
^
O insert main
bind 
^
H help main
bind 
^
F whereis main
bind 
^
G findnext main
bind 
^
B wherewas main
bind 
