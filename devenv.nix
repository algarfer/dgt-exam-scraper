{ pkgs, ... }:

{
  packages = [
    pkgs.git
    pkgs.uv
    pkgs.python313
  ];

  env.UV_PYTHON = "${pkgs.python313}/bin/python3.13";
  env.UV_PYTHON_DOWNLOADS = "never";
}
