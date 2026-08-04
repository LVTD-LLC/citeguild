package command

import (
	"bytes"
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/LVTD-LLC/citeguild/cli/internal/api"
)

type fakeClient struct {
	searchRequest api.SearchRequest
	searchResult  api.SearchResponse
	searchErr     error
	authChecked   bool
	authErr       error
}

func (f *fakeClient) Search(_ context.Context, request api.SearchRequest) (api.SearchResponse, error) {
	f.searchRequest = request
	return f.searchResult, f.searchErr
}

func (f *fakeClient) CheckAuth(_ context.Context) error {
	f.authChecked = true
	return f.authErr
}

type commandHarness struct {
	stdout  bytes.Buffer
	client  *fakeClient
	env     map[string]string
	base    string
	key     string
	timeout time.Duration
}

func newHarness() *commandHarness {
	return &commandHarness{
		client: &fakeClient{},
		env:    map[string]string{"CITEGUILD_API_KEY": "cg_secret_test"},
	}
}

func (h *commandHarness) deps() Dependencies {
	return Dependencies{
		Stdout: &h.stdout,
		LookupEnv: func(name string) (string, bool) {
			value, ok := h.env[name]
			return value, ok
		},
		NewClient: func(baseURL, apiKey string, timeout time.Duration) (Client, error) {
			h.base, h.key, h.timeout = baseURL, apiKey, timeout
			return h.client, nil
		},
		Version: VersionInfo{Version: "1.2.3", Commit: "abc123", Date: "2026-08-04"},
	}
}

func TestSearchRendersHumanAndStructuredOutput(t *testing.T) {
	tests := []struct {
		name string
		args []string
		want string
	}{
		{
			name: "human",
			args: []string{"search", "--limit", "3", "--language", "en", "--exclude-domain", "own.example", "django", "hooks"},
			want: "1. Hooks (member.example, relevance 0.988)\nhttps://member.example/hooks\nUse on_commit.\n",
		},
		{
			name: "json",
			args: []string{"search", "--json", "django hooks"},
			want: `{"contract_version":"v1","results":[{"article_id":"a1","title":"Hooks","canonical_url":"https://member.example/hooks","domain":"member.example","excerpt":"Use on_commit.","relevance":0.98765,"language":"en","last_seen_at":"2026-08-04T00:00:00Z"}]}` + "\n",
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			h := newHarness()
			h.client.searchResult = api.SearchResponse{ContractVersion: "v1", Results: []api.SearchResult{{
				ArticleID: "a1", Title: "Hooks", CanonicalURL: "https://member.example/hooks", Domain: "member.example", Excerpt: "Use on_commit.", Relevance: 0.98765, Language: "en", LastSeenAt: "2026-08-04T00:00:00Z",
			}}}
			if err := Execute(context.Background(), test.args, h.deps()); err != nil {
				t.Fatal(err)
			}
			if got := h.stdout.String(); got != test.want {
				t.Fatalf("stdout = %q, want %q", got, test.want)
			}
			if h.client.searchRequest.Query != "django hooks" {
				t.Fatalf("query = %q", h.client.searchRequest.Query)
			}
		})
	}
}

func TestSearchAssemblesCommandAndHTTPClientForAgentJSON(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.Method != http.MethodPost || request.URL.Path != "/v1/search" {
			t.Errorf("request = %s %s", request.Method, request.URL.Path)
		}
		if got := request.Header.Get("Authorization"); got != "Bearer cg_test_key" {
			t.Errorf("authorization = %q", got)
		}
		writer.Header().Set("Content-Type", "application/json")
		_, _ = writer.Write([]byte(`{"contract_version":"v1","results":[]}`))
	}))
	t.Cleanup(server.Close)

	var stdout bytes.Buffer
	deps := Dependencies{
		Stdout: &stdout,
		LookupEnv: func(name string) (string, bool) {
			if name == "CITEGUILD_API_KEY" {
				return "cg_test_key", true
			}
			return "", false
		},
		NewClient: func(baseURL, apiKey string, _ time.Duration) (Client, error) {
			return api.NewClient(server.Client(), baseURL, apiKey, "citeguild-cli/test")
		},
	}

	err := Execute(context.Background(), []string{"search", "--json", "--api-base", server.URL, "agent query"}, deps)
	if err != nil {
		t.Fatal(err)
	}
	if got, want := stdout.String(), `{"contract_version":"v1","results":[]}`+"\n"; got != want {
		t.Fatalf("stdout = %q, want %q", got, want)
	}
}

func TestDefaultHTTPClientRefusesRedirectsWithCredentials(t *testing.T) {
	targetCalled := false
	target := httptest.NewServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		targetCalled = true
	}))
	t.Cleanup(target.Close)
	redirect := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		http.Redirect(writer, request, target.URL, http.StatusFound)
	}))
	t.Cleanup(redirect.Close)

	var stdout bytes.Buffer
	deps := NewDefaultDependencies(&stdout, VersionInfo{Version: "test"})
	deps.LookupEnv = func(name string) (string, bool) {
		return map[string]string{"CITEGUILD_API_KEY": "redirect-secret"}[name], name == "CITEGUILD_API_KEY"
	}
	err := Execute(context.Background(), []string{"search", "--api-base", redirect.URL, "query"}, deps)
	if got := ExitCode(err); got != ExitServer {
		t.Fatalf("exit = %d, error = %v", got, err)
	}
	if targetCalled {
		t.Fatal("redirect target received a request")
	}
	if stdout.Len() != 0 {
		t.Fatalf("stdout = %q", stdout.String())
	}
}

func TestSearchRejectsInvalidUsageBeforeCallingClient(t *testing.T) {
	tests := []struct {
		name string
		args []string
	}{
		{name: "missing query", args: []string{"search"}},
		{name: "limit", args: []string{"search", "--limit", "51", "query"}},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			h := newHarness()
			err := Execute(context.Background(), test.args, h.deps())
			if ExitCode(err) != ExitUsage {
				t.Fatalf("exit = %d, error = %v", ExitCode(err), err)
			}
			if h.key != "" {
				t.Fatal("client was constructed for invalid input")
			}
		})
	}
}

func TestConfigStatusNeverPrintsAPIKey(t *testing.T) {
	h := newHarness()
	h.env["CITEGUILD_API_BASE"] = "https://staging.example/api"
	h.env["CITEGUILD_TIMEOUT"] = "7s"
	if err := Execute(context.Background(), []string{"config", "status", "--json"}, h.deps()); err != nil {
		t.Fatal(err)
	}
	got := h.stdout.String()
	if got != `{"api_base":"https://staging.example/api","api_key_set":true,"timeout":"7s"}`+"\n" {
		t.Fatalf("stdout = %q", got)
	}
	if strings.Contains(got, h.env["CITEGUILD_API_KEY"]) {
		t.Fatal("config output leaked API key")
	}
}

func TestConfigStatusRejectsUnsafeAPIBase(t *testing.T) {
	h := newHarness()
	err := Execute(context.Background(), []string{"config", "status", "--api-base", "https://user:secret@example.test/api"}, h.deps())
	if ExitCode(err) != ExitUsage || !strings.Contains(err.Error(), "must not contain credentials") {
		t.Fatalf("exit = %d, error = %v", ExitCode(err), err)
	}
	if strings.Contains(err.Error(), "secret@example") {
		t.Fatalf("error leaked URL credentials: %q", err)
	}
}

func TestAuthStatusChecksCredential(t *testing.T) {
	h := newHarness()
	if err := Execute(context.Background(), []string{"auth", "status", "--json"}, h.deps()); err != nil {
		t.Fatal(err)
	}
	if !h.client.authChecked {
		t.Fatal("authentication was not checked")
	}
	if got := h.stdout.String(); got != `{"authenticated":true,"api_base":"https://citeguild.lvtd.dev/api"}`+"\n" {
		t.Fatalf("stdout = %q", got)
	}
}

func TestExitCodesDistinguishFailureClasses(t *testing.T) {
	tests := []struct {
		name string
		err  error
		want int
	}{
		{name: "validation", err: &api.Error{Kind: api.ErrorValidation, Message: "invalid"}, want: ExitUsage},
		{name: "auth", err: &api.Error{Kind: api.ErrorAuth, Message: "auth"}, want: ExitAuth},
		{name: "network", err: &api.Error{Kind: api.ErrorNetwork, Message: "network"}, want: ExitNetwork},
		{name: "cancel", err: &api.Error{Kind: api.ErrorNetwork, Message: "cancel", Err: context.Canceled}, want: ExitInterrupted},
		{name: "server", err: &api.Error{Kind: api.ErrorServer, Message: "server"}, want: ExitServer},
		{name: "protocol", err: &api.Error{Kind: api.ErrorProtocol, Message: "protocol"}, want: ExitServer},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			h := newHarness()
			h.client.searchErr = test.err
			err := Execute(context.Background(), []string{"search", "query"}, h.deps())
			if got := ExitCode(err); got != test.want {
				t.Fatalf("exit = %d, want %d, error = %v", got, test.want, err)
			}
		})
	}
}

func TestJSONFailureRendersStableDiagnosticOnStderr(t *testing.T) {
	h := newHarness()
	h.client.searchErr = &api.Error{Kind: api.ErrorServer, Code: "rate_limited", Message: "Try later", RequestID: "req-1", Retryable: true, RetryAfterSeconds: 30}
	err := Execute(context.Background(), []string{"search", "--json", "query"}, h.deps())
	if ExitCode(err) != ExitServer || h.stdout.Len() != 0 {
		t.Fatalf("exit = %d, stdout = %q", ExitCode(err), h.stdout.String())
	}
	var stderr bytes.Buffer
	RenderError(&stderr, err)
	if got, want := stderr.String(), `{"code":"rate_limited","message":"Try later","request_id":"req-1","retryable":true,"retry_after_seconds":30,"exit_code":5}`+"\n"; got != want {
		t.Fatalf("stderr = %q, want %q", got, want)
	}
}

func TestSearchQueryLimitCountsUnicodeCharacters(t *testing.T) {
	h := newHarness()
	if err := Execute(context.Background(), []string{"search", strings.Repeat("界", 8000)}, h.deps()); err != nil {
		t.Fatal(err)
	}
	err := Execute(context.Background(), []string{"search", strings.Repeat("界", 8001)}, h.deps())
	if ExitCode(err) != ExitUsage {
		t.Fatalf("exit = %d, error = %v", ExitCode(err), err)
	}
}

func TestMissingCredentialIsAuthenticationFailure(t *testing.T) {
	h := newHarness()
	delete(h.env, "CITEGUILD_API_KEY")
	err := Execute(context.Background(), []string{"search", "query"}, h.deps())
	if ExitCode(err) != ExitAuth || !strings.Contains(err.Error(), "CITEGUILD_API_KEY") {
		t.Fatalf("exit = %d, error = %v", ExitCode(err), err)
	}
}

func TestRenderErrorIncludesSafeRequestIDAndUsage(t *testing.T) {
	apiErr := &api.Error{Kind: api.ErrorAuth, Message: "Authentication required.", RequestID: "req-123"}
	err := &Error{ExitCode: ExitAuth, Message: apiErr.Message, Usage: "Usage: citeguild test\n", Err: apiErr}
	var output bytes.Buffer
	RenderError(&output, err)
	if got, want := output.String(), "citeguild: Authentication required.\nrequest id: req-123\nUsage: citeguild test\n"; got != want {
		t.Fatalf("output = %q, want %q", got, want)
	}
}

func TestHumanOutputRemovesTerminalControlsFromRemoteText(t *testing.T) {
	response := api.SearchResponse{ContractVersion: "v1", Results: []api.SearchResult{{
		Title:        "\x1b[31mUnsafe\nTitle",
		Domain:       "member.example\rspoofed",
		CanonicalURL: "https://member.example/article\tcontinued",
		Excerpt:      "Safe\x00 excerpt",
		Relevance:    0.5,
	}}}
	var output bytes.Buffer
	if err := renderSearch(&output, response); err != nil {
		t.Fatal(err)
	}
	if strings.ContainsRune(output.String(), '\x1b') || strings.ContainsRune(output.String(), '\x00') {
		t.Fatalf("human output contains terminal controls: %q", output.String())
	}
	if got, want := output.String(), "1. [31mUnsafe Title (member.example spoofed, relevance 0.500)\nhttps://member.example/article continued\nSafe excerpt\n"; got != want {
		t.Fatalf("output = %q, want %q", got, want)
	}
}

func TestVersionAndHelpDoNotConstructClient(t *testing.T) {
	for _, args := range [][]string{{"--help"}, {"--version"}, {"version", "--json"}} {
		h := newHarness()
		if err := Execute(context.Background(), args, h.deps()); err != nil {
			t.Fatal(err)
		}
		if h.key != "" {
			t.Fatal("bootstrap command constructed API client")
		}
	}
}

func TestExitCodePreservesWrappedErrors(t *testing.T) {
	err := &Error{ExitCode: ExitAuth, Message: "auth", Err: errors.New("cause")}
	if got := ExitCode(joinedError(err)); got != ExitAuth {
		t.Fatalf("exit = %d", got)
	}
}

func joinedError(err error) error {
	return errors.Join(errors.New("outer context"), err)
}
