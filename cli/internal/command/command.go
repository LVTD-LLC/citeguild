package command

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"syscall"
	"time"
	"unicode"
	"unicode/utf8"

	"github.com/LVTD-LLC/citeguild/cli/internal/api"
)

const (
	ExitOK          = 0
	ExitInternal    = 1
	ExitUsage       = 2
	ExitAuth        = 3
	ExitNetwork     = 4
	ExitServer      = 5
	ExitInterrupted = 130

	DefaultAPIBase = "https://citeguild.lvtd.dev/api"
	DefaultTimeout = 15 * time.Second
)

type LookupEnv func(string) (string, bool)

type VersionInfo struct {
	Version string `json:"version"`
	Commit  string `json:"commit"`
	Date    string `json:"date"`
}

type Client interface {
	Search(context.Context, api.SearchRequest) (api.SearchResponse, error)
	CheckAuth(context.Context) error
}

type ClientFactory func(baseURL, apiKey string, timeout time.Duration) (Client, error)

type Dependencies struct {
	Stdout    io.Writer
	LookupEnv LookupEnv
	NewClient ClientFactory
	Version   VersionInfo
}

type Error struct {
	ExitCode int
	Message  string
	Usage    string
	JSON     bool
	Err      error
}

func (e *Error) Error() string {
	if e.Message != "" {
		return e.Message
	}
	if e.Err != nil {
		return e.Err.Error()
	}
	return "command failed"
}

func (e *Error) Unwrap() error { return e.Err }

func Execute(ctx context.Context, args []string, deps Dependencies) error {
	if deps.Stdout == nil || deps.LookupEnv == nil || deps.NewClient == nil {
		return &Error{ExitCode: ExitInternal, Message: "CLI dependencies are not configured"}
	}
	if len(args) == 0 {
		return writeRootHelp(deps.Stdout)
	}

	switch args[0] {
	case "help", "-h", "--help":
		return writeRootHelp(deps.Stdout)
	case "-v", "--version":
		return executeVersion(args[1:], deps)
	case "search":
		return executeSearch(ctx, args[1:], deps)
	case "config":
		return executeConfig(args[1:], deps)
	case "auth":
		return executeAuth(ctx, args[1:], deps)
	case "version":
		return executeVersion(args[1:], deps)
	default:
		return usageError(fmt.Sprintf("unknown command %q", args[0]), rootUsage())
	}
}

type commonOptions struct {
	apiBase string
	timeout time.Duration
	json    bool
}

type searchOptions struct {
	commonOptions
	limit           int
	language        string
	excludedDomains stringList
}

func executeSearch(ctx context.Context, args []string, deps Dependencies) error {
	usage := searchUsage()
	fs := flag.NewFlagSet("search", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	opts := searchOptions{}
	addCommonFlags(fs, &opts.commonOptions, deps.LookupEnv)
	fs.IntVar(&opts.limit, "limit", 10, "maximum number of results (1-50)")
	fs.StringVar(&opts.language, "language", "", "optional BCP 47 language tag")
	fs.Var(&opts.excludedDomains, "exclude-domain", "exact domain to exclude (repeat up to 20 times)")
	if err := fs.Parse(args); err != nil {
		if errors.Is(err, flag.ErrHelp) {
			return writeText(deps.Stdout, usage)
		}
		return usageError(err.Error(), usage)
	}
	if fs.NArg() == 0 {
		return usageError("search query is required", usage)
	}
	query := strings.TrimSpace(strings.Join(fs.Args(), " "))
	if query == "" {
		return usageError("search query is required", usage)
	}
	if utf8.RuneCountInString(query) > 8000 {
		return usageError("search query must be at most 8000 characters", usage)
	}
	if opts.limit < 1 || opts.limit > 50 {
		return usageError("--limit must be between 1 and 50", usage)
	}
	if utf8.RuneCountInString(opts.language) > 35 {
		return usageError("--language must be at most 35 characters", usage)
	}
	if len(opts.excludedDomains) > 20 {
		return usageError("--exclude-domain may be repeated at most 20 times", usage)
	}

	client, err := configuredClient(opts.commonOptions, deps)
	if err != nil {
		return withJSON(err, opts.json)
	}
	result, err := client.Search(ctx, api.SearchRequest{
		Query:           query,
		Limit:           opts.limit,
		Language:        opts.language,
		ExcludedDomains: opts.excludedDomains,
	})
	if err != nil {
		return withJSON(classifyClientError(err), opts.json)
	}
	if opts.json {
		return encodeJSON(deps.Stdout, result)
	}
	return renderSearch(deps.Stdout, result)
}

func executeConfig(args []string, deps Dependencies) error {
	if len(args) == 0 || args[0] != "status" {
		if len(args) == 1 && isHelp(args[0]) {
			return writeText(deps.Stdout, configUsage())
		}
		return usageError("config requires the status command", configUsage())
	}
	usage := configUsage()
	fs := flag.NewFlagSet("config status", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	opts := commonOptions{}
	addCommonFlags(fs, &opts, deps.LookupEnv)
	if err := fs.Parse(args[1:]); err != nil {
		if errors.Is(err, flag.ErrHelp) {
			return writeText(deps.Stdout, usage)
		}
		return usageError(err.Error(), usage)
	}
	if fs.NArg() != 0 {
		return usageError("config status does not accept operands", usage)
	}
	if err := validateCommon(opts); err != nil {
		return err
	}
	apiKey, keySet := deps.LookupEnv("CITEGUILD_API_KEY")
	keySet = keySet && strings.TrimSpace(apiKey) != ""
	status := struct {
		APIBase   string `json:"api_base"`
		APIKeySet bool   `json:"api_key_set"`
		Timeout   string `json:"timeout"`
	}{opts.apiBase, keySet, opts.timeout.String()}
	if opts.json {
		return encodeJSON(deps.Stdout, status)
	}
	keyStatus := "not set"
	if keySet {
		keyStatus = "set"
	}
	_, err := fmt.Fprintf(deps.Stdout, "API base: %s\nAPI key: %s\nTimeout: %s\n", opts.apiBase, keyStatus, opts.timeout)
	return err
}

func executeAuth(ctx context.Context, args []string, deps Dependencies) error {
	if len(args) == 0 || args[0] != "status" {
		if len(args) == 1 && isHelp(args[0]) {
			return writeText(deps.Stdout, authUsage())
		}
		return usageError("auth requires the status command", authUsage())
	}
	usage := authUsage()
	fs := flag.NewFlagSet("auth status", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	opts := commonOptions{}
	addCommonFlags(fs, &opts, deps.LookupEnv)
	if err := fs.Parse(args[1:]); err != nil {
		if errors.Is(err, flag.ErrHelp) {
			return writeText(deps.Stdout, usage)
		}
		return usageError(err.Error(), usage)
	}
	if fs.NArg() != 0 {
		return usageError("auth status does not accept operands", usage)
	}
	client, err := configuredClient(opts, deps)
	if err != nil {
		return withJSON(err, opts.json)
	}
	if err := client.CheckAuth(ctx); err != nil {
		return withJSON(classifyClientError(err), opts.json)
	}
	if opts.json {
		return encodeJSON(deps.Stdout, struct {
			Authenticated bool   `json:"authenticated"`
			APIBase       string `json:"api_base"`
		}{true, opts.apiBase})
	}
	_, err = fmt.Fprintf(deps.Stdout, "Authenticated with %s\n", opts.apiBase)
	return err
}

func executeVersion(args []string, deps Dependencies) error {
	usage := versionUsage()
	fs := flag.NewFlagSet("version", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	asJSON := fs.Bool("json", false, "emit structured JSON")
	if err := fs.Parse(args); err != nil {
		if errors.Is(err, flag.ErrHelp) {
			return writeText(deps.Stdout, usage)
		}
		return usageError(err.Error(), usage)
	}
	if fs.NArg() != 0 {
		return usageError("version does not accept operands", usage)
	}
	if *asJSON {
		return encodeJSON(deps.Stdout, deps.Version)
	}
	_, err := fmt.Fprintf(deps.Stdout, "citeguild %s (commit %s, built %s)\n", deps.Version.Version, deps.Version.Commit, deps.Version.Date)
	return err
}

func addCommonFlags(fs *flag.FlagSet, opts *commonOptions, lookup LookupEnv) {
	apiBase := envOrDefault(lookup, "CITEGUILD_API_BASE", DefaultAPIBase)
	timeout := envDurationOrDefault(lookup, "CITEGUILD_TIMEOUT", DefaultTimeout)
	fs.StringVar(&opts.apiBase, "api-base", apiBase, "CiteGuild API base URL")
	fs.DurationVar(&opts.timeout, "timeout", timeout, "total request timeout")
	fs.BoolVar(&opts.json, "json", false, "emit structured JSON")
}

func configuredClient(opts commonOptions, deps Dependencies) (Client, error) {
	if err := validateCommon(opts); err != nil {
		return nil, err
	}
	apiKey, ok := deps.LookupEnv("CITEGUILD_API_KEY")
	apiKey = strings.TrimSpace(apiKey)
	if !ok || apiKey == "" {
		return nil, &Error{ExitCode: ExitAuth, Message: "CITEGUILD_API_KEY is not set; export an API key from CiteGuild settings"}
	}
	client, err := deps.NewClient(opts.apiBase, apiKey, opts.timeout)
	if err != nil {
		return nil, &Error{ExitCode: ExitUsage, Message: err.Error(), Err: err}
	}
	return client, nil
}

func validateCommon(opts commonOptions) error {
	if strings.TrimSpace(opts.apiBase) == "" {
		return &Error{ExitCode: ExitUsage, Message: "API base URL must not be empty"}
	}
	if err := api.ValidateBaseURL(opts.apiBase); err != nil {
		return &Error{ExitCode: ExitUsage, Message: err.Error(), Err: err}
	}
	if opts.timeout <= 0 {
		return &Error{ExitCode: ExitUsage, Message: "timeout must be greater than zero"}
	}
	return nil
}

func classifyClientError(err error) error {
	var apiErr *api.Error
	if !errors.As(err, &apiErr) {
		return &Error{ExitCode: ExitInternal, Message: "Unexpected CLI failure", Err: err}
	}
	code := ExitServer
	switch apiErr.Kind {
	case api.ErrorValidation:
		code = ExitUsage
	case api.ErrorAuth:
		code = ExitAuth
	case api.ErrorNetwork:
		if errors.Is(apiErr, context.Canceled) {
			code = ExitInterrupted
		} else {
			code = ExitNetwork
		}
	}
	return &Error{ExitCode: code, Message: apiErr.Message, Err: apiErr}
}

func withJSON(err error, enabled bool) error {
	var commandErr *Error
	if enabled && errors.As(err, &commandErr) {
		commandErr.JSON = true
	}
	return err
}

func ExitCode(err error) int {
	if err == nil || errors.Is(err, syscall.EPIPE) {
		return ExitOK
	}
	var commandErr *Error
	if errors.As(err, &commandErr) {
		return commandErr.ExitCode
	}
	return ExitInternal
}

func RenderError(writer io.Writer, err error) {
	if err == nil || errors.Is(err, syscall.EPIPE) {
		return
	}
	var commandErr *Error
	if errors.As(err, &commandErr) {
		if commandErr.JSON {
			apiErr := &api.Error{}
			hasAPIError := errors.As(commandErr, &apiErr)
			code := map[int]string{ExitInternal: "internal_error", ExitUsage: "validation_error", ExitAuth: "authentication_error", ExitNetwork: "network_error", ExitServer: "server_error", ExitInterrupted: "interrupted"}[commandErr.ExitCode]
			if hasAPIError && apiErr.Code != "" {
				code = apiErr.Code
			}
			_ = encodeJSON(writer, struct {
				Code              string `json:"code"`
				Message           string `json:"message"`
				RequestID         string `json:"request_id,omitempty"`
				Retryable         bool   `json:"retryable"`
				RetryAfterSeconds int    `json:"retry_after_seconds,omitempty"`
				ExitCode          int    `json:"exit_code"`
			}{code, commandErr.Message, apiErr.RequestID, hasAPIError && apiErr.Retryable, apiErr.RetryAfterSeconds, commandErr.ExitCode})
			return
		}
		fmt.Fprintf(writer, "citeguild: %s\n", sanitizeHuman(commandErr.Message))
		var apiErr *api.Error
		if errors.As(commandErr, &apiErr) && apiErr.RequestID != "" {
			fmt.Fprintf(writer, "request id: %s\n", sanitizeHuman(apiErr.RequestID))
		}
		if commandErr.Usage != "" {
			fmt.Fprint(writer, commandErr.Usage)
		}
		return
	}
	fmt.Fprintln(writer, "citeguild: unexpected internal error")
}

func renderSearch(writer io.Writer, response api.SearchResponse) error {
	if len(response.Results) == 0 {
		return writeText(writer, "No relevant member articles found.\n")
	}
	for index, result := range response.Results {
		if index > 0 {
			if _, err := fmt.Fprintln(writer); err != nil {
				return err
			}
		}
		if _, err := fmt.Fprintf(
			writer,
			"%d. %s (%s, relevance %.3f)\n%s\n%s\n",
			index+1,
			sanitizeHuman(result.Title),
			sanitizeHuman(result.Domain),
			result.Relevance,
			sanitizeHuman(result.CanonicalURL),
			sanitizeHuman(result.Excerpt),
		); err != nil {
			return err
		}
	}
	return nil
}

func encodeJSON(writer io.Writer, value any) error {
	encoder := json.NewEncoder(writer)
	encoder.SetEscapeHTML(false)
	return encoder.Encode(value)
}

func sanitizeHuman(value string) string {
	withoutControls := strings.Map(func(character rune) rune {
		if unicode.Is(unicode.C, character) {
			return ' '
		}
		return character
	}, value)
	return strings.Join(strings.Fields(withoutControls), " ")
}

type stringList []string

func (s *stringList) String() string { return strings.Join(*s, ",") }

func (s *stringList) Set(value string) error {
	value = strings.TrimSpace(value)
	if value == "" {
		return errors.New("domain must not be empty")
	}
	*s = append(*s, value)
	return nil
}

func envOrDefault(lookup LookupEnv, name, fallback string) string {
	if value, ok := lookup(name); ok {
		return value
	}
	return fallback
}

func envDurationOrDefault(lookup LookupEnv, name string, fallback time.Duration) time.Duration {
	value, ok := lookup(name)
	if !ok {
		return fallback
	}
	parsed, err := time.ParseDuration(value)
	if err != nil {
		return 0
	}
	return parsed
}

func usageError(message, usage string) error {
	return &Error{ExitCode: ExitUsage, Message: message, Usage: usage}
}

func isHelp(value string) bool { return value == "help" || value == "-h" || value == "--help" }

func writeText(writer io.Writer, value string) error {
	_, err := io.WriteString(writer, value)
	return err
}

func rootUsage() string {
	return `Usage: citeguild <command> [options]

Search CiteGuild's active member articles from agents, scripts, and shells.

Commands:
  search         Search for relevant member articles
  auth status    Verify the configured API key
  config status  Show secret-safe local configuration
  version        Show CLI version information (also --version)

Run "citeguild <command> --help" for command-specific options.
`
}

func searchUsage() string {
	return `Usage: citeguild search [options] <query or draft passage>

Options must appear before the query. Query words are joined with spaces.

Options:
  --api-base URL           API base (env CITEGUILD_API_BASE)
  --timeout DURATION       total request timeout (env CITEGUILD_TIMEOUT; default 15s)
  --limit NUMBER           maximum results, 1-50 (default 10)
  --language TAG           optional BCP 47 language tag
  --exclude-domain DOMAIN  exact domain to exclude; repeat up to 20 times
  --json                   emit the stable v1 search response as JSON

Authentication comes only from CITEGUILD_API_KEY.
`
}

func configUsage() string {
	return `Usage: citeguild config status [options]

Show the resolved API URL, timeout, and whether an API key is set. The key is
never printed.

Options:
  --api-base URL      API base (env CITEGUILD_API_BASE)
  --timeout DURATION  total request timeout (env CITEGUILD_TIMEOUT; default 15s)
  --json              emit structured JSON
`
}

func authUsage() string {
	return `Usage: citeguild auth status [options]

Verify CITEGUILD_API_KEY against the configured CiteGuild API.

Options:
  --api-base URL      API base (env CITEGUILD_API_BASE)
  --timeout DURATION  total request timeout (env CITEGUILD_TIMEOUT; default 15s)
  --json              emit structured JSON
`
}

func versionUsage() string {
	return `Usage: citeguild version [--json]

Show version, commit, and build date.
`
}

func writeRootHelp(writer io.Writer) error { return writeText(writer, rootUsage()) }

func NewDefaultDependencies(stdout io.Writer, version VersionInfo) Dependencies {
	return Dependencies{
		Stdout:    stdout,
		LookupEnv: os.LookupEnv,
		Version:   version,
		NewClient: func(baseURL, apiKey string, timeout time.Duration) (Client, error) {
			transport := http.DefaultTransport.(*http.Transport).Clone()
			httpClient := &http.Client{
				Transport: transport,
				Timeout:   timeout,
				CheckRedirect: func(_ *http.Request, _ []*http.Request) error {
					return http.ErrUseLastResponse
				},
			}
			return api.NewClient(httpClient, baseURL, apiKey, "citeguild-cli/"+version.Version)
		},
	}
}
