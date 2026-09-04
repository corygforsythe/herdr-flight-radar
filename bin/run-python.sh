#!/bin/sh
# Herdr's plugin runtime can spawn commands with a minimal PATH (observed:
# /usr/bin:/bin:/usr/sbin:/sbin) that omits Homebrew and other common
# install locations. /usr/bin/python3 (Apple's system Python) is already on
# that minimal PATH, so this mostly guards against machines where it isn't.
# It also extends PATH so the plugin's own dump1090 lookup (shutil.which)
# can find a Homebrew-installed dump1090 binary.
for extra in /opt/homebrew/bin /usr/local/bin "$HOME/.local/bin"; do
  case ":$PATH:" in
    *":$extra:"*) ;;
    *) [ -d "$extra" ] && PATH="$extra:$PATH" ;;
  esac
done
export PATH

script="$1"
shift
exec python3 "$script" "$@"
