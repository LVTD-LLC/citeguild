package api

import (
	"context"
	"errors"
	"io"
	"net/http"
	"strings"
	"testing"
)

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(request *http.Request) (*http.Response, error) {
	return f(request)
}

type trackingBody struct {
	io.Reader
	closed bool
}

func (b *trackingBody) Close() error {
	b.closed = true
	return nil
}

func TestSearchSendsAuthenticatedV1RequestAndDecodesResponse(t *testing.T) {
	const secret = "cg_secret_test_value"
	client, err := NewClient(&http.Client{Transport: roundTripFunc(func(request *http.Request) (*http.Response, error) {
		if request.Method != http.MethodPost || request.URL.String() != "https://example.test/api/v1/search" {
			t.Fatalf("request = %s %s", request.Method, request.URL.String())
		}
		if got := request.Header.Get("Authorization"); got != "Bearer "+secret {
			t.Fatalf("authorization = %q", got)
		}
		if got := request.Header.Get("User-Agent"); got != "citeguild-cli/test" {
			t.Fatalf("user-agent = %q", got)
		}
		body, readErr := io.ReadAll(request.Body)
		if readErr != nil {
			t.Fatal(readErr)
		}
		if got, want := string(body), `{"query":"transaction hooks","limit":3,"language":"en","excluded_domains":["own.example"]}`; got != want {
			t.Fatalf("body = %s, want %s", got, want)
		}
		return jsonResponse(http.StatusOK, `{"contract_version":"v1","results":[{"article_id":"a1","title":"Hooks","canonical_url":"https://member.example/hooks","domain":"member.example","excerpt":"Use on_commit.","relevance":0.9,"language":"en","last_seen_at":"2026-08-04T00:00:00Z"}]}`), nil
	})}, "https://example.test/api/", secret, "citeguild-cli/test")
	if err != nil {
		t.Fatal(err)
	}

	result, err := client.Search(context.Background(), SearchRequest{
		Query:           "transaction hooks",
		Limit:           3,
		Language:        "en",
		ExcludedDomains: []string{"own.example"},
	})
	if err != nil {
		t.Fatal(err)
	}
	if result.ContractVersion != "v1" || len(result.Results) != 1 || result.Results[0].Title != "Hooks" {
		t.Fatalf("unexpected response: %#v", result)
	}
}

func TestSearchClassifiesSafeAPIErrorWithoutLeakingSecret(t *testing.T) {
	const secret = "cg_secret_never_render"
	client, err := NewClient(&http.Client{Transport: roundTripFunc(func(_ *http.Request) (*http.Response, error) {
		response := jsonResponse(http.StatusUnauthorized, `{"code":"authentication_required","message":"Rejected cg_secret_never_render","request_id":"req-cg_secret_never_render","retryable":false}`)
		response.Header.Set("X-Debug-Secret", secret)
		return response, nil
	})}, "https://example.test/api", secret, "test")
	if err != nil {
		t.Fatal(err)
	}

	_, err = client.Search(context.Background(), SearchRequest{Query: "private query", Limit: 10})
	var apiErr *Error
	if !errors.As(err, &apiErr) {
		t.Fatalf("error = %T %v", err, err)
	}
	if apiErr.Kind != ErrorAuth || apiErr.StatusCode != http.StatusUnauthorized || apiErr.RequestID != "req-[REDACTED]" {
		t.Fatalf("classified error = %#v", apiErr)
	}
	if strings.Contains(err.Error(), secret) || strings.Contains(err.Error(), "private query") {
		t.Fatalf("error leaked sensitive input: %q", err)
	}
}

func TestSearchRejectsOversizedAndUnsupportedResponses(t *testing.T) {
	tests := []struct {
		name string
		body string
	}{
		{name: "oversized", body: strings.Repeat("x", maxSuccessBody+1)},
		{name: "unsupported contract", body: `{"contract_version":"v2","results":[]}`},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			client, err := NewClient(&http.Client{Transport: roundTripFunc(func(_ *http.Request) (*http.Response, error) {
				return jsonResponse(http.StatusOK, test.body), nil
			})}, "https://example.test/api", "secret", "test")
			if err != nil {
				t.Fatal(err)
			}
			_, err = client.Search(context.Background(), SearchRequest{Query: "query", Limit: 10})
			var apiErr *Error
			if !errors.As(err, &apiErr) || apiErr.Kind != ErrorProtocol {
				t.Fatalf("error = %T %#v", err, err)
			}
		})
	}
}

func TestSearchPreservesBoundedRetryAfterGuidance(t *testing.T) {
	client, err := NewClient(&http.Client{Transport: roundTripFunc(func(_ *http.Request) (*http.Response, error) {
		response := jsonResponse(http.StatusTooManyRequests, `{"code":"rate_limited","message":"Try later","retryable":true}`)
		response.Header.Set("Retry-After", "30")
		return response, nil
	})}, "https://example.test/api", "secret", "test")
	if err != nil {
		t.Fatal(err)
	}
	_, err = client.Search(context.Background(), SearchRequest{Query: "query", Limit: 10})
	var apiErr *Error
	if !errors.As(err, &apiErr) || apiErr.RetryAfterSeconds != 30 {
		t.Fatalf("error = %#v", err)
	}
}

func TestCheckAuthClassifiesTransportCancellation(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	client, err := NewClient(&http.Client{Transport: roundTripFunc(func(_ *http.Request) (*http.Response, error) {
		return nil, context.Canceled
	})}, "https://example.test/api", "secret", "test")
	if err != nil {
		t.Fatal(err)
	}
	err = client.CheckAuth(ctx)
	var apiErr *Error
	if !errors.As(err, &apiErr) || apiErr.Kind != ErrorNetwork || !errors.Is(err, context.Canceled) {
		t.Fatalf("error = %T %#v", err, err)
	}
}

func TestCheckAuthClosesSuccessfulResponseBody(t *testing.T) {
	body := &trackingBody{Reader: strings.NewReader(`{"profile":{"id":1}}`)}
	client, err := NewClient(&http.Client{Transport: roundTripFunc(func(_ *http.Request) (*http.Response, error) {
		return &http.Response{
			StatusCode: http.StatusOK,
			Header:     http.Header{"Content-Type": []string{"application/json"}},
			Body:       body,
		}, nil
	})}, "https://example.test/api", "secret", "test")
	if err != nil {
		t.Fatal(err)
	}
	if err := client.CheckAuth(context.Background()); err != nil {
		t.Fatal(err)
	}
	if !body.closed {
		t.Fatal("response body was not closed")
	}
}

func TestNewClientRejectsUnsafeBaseURLs(t *testing.T) {
	for _, baseURL := range []string{"example.test/api", "ftp://example.test/api", "http://example.test/api", "https://user:pass@example.test/api", "https://example.test/api?token=x", "https://example.test/%zz-secret"} {
		t.Run(baseURL, func(t *testing.T) {
			if _, err := NewClient(http.DefaultClient, baseURL, "secret", "test"); err == nil {
				t.Fatalf("NewClient(%q) succeeded", baseURL)
			}
		})
	}
}

func TestNewClientAllowsLoopbackHTTP(t *testing.T) {
	for _, baseURL := range []string{"http://localhost:8000/api", "http://127.0.0.1:8000/api", "http://[::1]:8000/api"} {
		if _, err := NewClient(http.DefaultClient, baseURL, "secret", "test"); err != nil {
			t.Fatalf("NewClient(%q): %v", baseURL, err)
		}
	}
}

func jsonResponse(status int, body string) *http.Response {
	return &http.Response{
		StatusCode: status,
		Header:     http.Header{"Content-Type": []string{"application/json"}},
		Body:       io.NopCloser(strings.NewReader(body)),
	}
}
