{ pkgs ? import (fetchTarball https://github.com/NixOS/nixpkgs/archive/3024ba0b76bf451d38b1ef83be7f4b525671329b.tar.gz) { }
}:
let
  foo = "foo";
in
  pkgs.mkShell {
    buildInputs = [
      pkgs.bashInteractive
      pkgs.wget
      pkgs.gawk
      pkgs.fasttext
    ];
    shellHook = ''
    '';
  }
