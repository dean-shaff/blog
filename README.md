## Blog

My personal blog

### Installation

We need ruby development files, as some of the Ruby gems we need use C extensions. On Ubuntu:

```
sudo apt install ruby-full
```

Then we want to set up `gem` such that it doesn't try to install globally:

```
echo export GEM_HOME="$HOME/.gem" >> ~/.bash_aliases
```

Or, use rbenv:

```
brew install rbenv
```

Then add `eval "$(rbenv init - zsh)"` to your `~/.zshrc`. 

Install the latest version of ruby: 

```
rbenv install 3.3.1
rbenv local 3.3.1
```

Now let's install bundler:

```
gem install bundler
```

Okie dokie, now let's try to install the blog:

```
bundle install
```

Now we can run it locally!

```
bundle exec jekyll serve
```
