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
