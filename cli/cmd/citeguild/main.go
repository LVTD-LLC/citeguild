package main

import (
	"context"
	"os"
	"os/signal"

	"github.com/LVTD-LLC/citeguild/cli/internal/command"
)

var (
	version = "dev"
	commit  = "unknown"
	date    = "unknown"
)

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()

	deps := command.NewDefaultDependencies(os.Stdout, command.VersionInfo{
		Version: version,
		Commit:  commit,
		Date:    date,
	})
	err := command.Execute(ctx, os.Args[1:], deps)
	command.RenderError(os.Stderr, err)
	os.Exit(command.ExitCode(err))
}
