{
  description = "coupled: check the COUPLED:<key>: <label> markers in a repository against its registry, and that their relations hold";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
  # COUPLED:cli-kit-version: flake /cli-kit\/(v[0-9.]+)/
  inputs.cli-kit = { url = "github:ianflanagan1/cli-kit/v0.1.0"; flake = false; };
  # COUPLED:repo-settings-version: flake /repo-settings\/(v[0-9.]+)/
  inputs.repo-settings = { url = "github:ianflanagan1/repo-settings/v0.1.0"; flake = false; };
  # COUPLED:git-default-branch-version: flake /git-default-branch\/(v[0-9.]+)/
  inputs.git-default-branch = { url = "github:ianflanagan1/git-default-branch/v0.1.0"; flake = false; };

  outputs = { self, nixpkgs, cli-kit, repo-settings, git-default-branch }:
    let
      systems = [ "aarch64-darwin" "x86_64-darwin" "aarch64-linux" "x86_64-linux" ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      packages = forAllSystems (pkgs: rec {
        # Python and the tools the lint calls are pinned, so it behaves the same on macOS, Linux and CI.
        # cli-kit and git-default-branch use only the standard library, so their source on the path
        # is all they need; repo-settings, which reads the settings file, also imports tomlkit.
        coupled = let
          python = pkgs.python313.withPackages (packages: [ packages.tomlkit ]);
        in pkgs.writeShellApplication {
          name = "coupled";
          runtimeInputs = [ pkgs.git pkgs.gnugrep ];
          text = ''
            PYTHONPATH=${./src}:${cli-kit}/src:${repo-settings}/src:${git-default-branch}/src exec ${python}/bin/python3 -s -P -m coupled "$@"
          '';
        };
        default = coupled;
      });
    };
}
