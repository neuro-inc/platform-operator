package tokenfilter

import (
	"context"
	"encoding/base64"
	"net/http"
	"net/http/httptest"
	"reflect"
	"strconv"
	"strings"
	"testing"
)

func testConfig() *Config {
	return &Config{
		Cookies:        []string{"sat", "srt", "dat", "drt", "launchpad-token"},
		CookiePatterns: []string{"^launchpad-[0-9a-f]+-token$"},
		BearerClaims:   []string{"https://platform.neuromation.io/user"},
	}
}

func testJWT(payload string) string {
	enc := base64.RawURLEncoding
	return enc.EncodeToString([]byte(`{"alg":"HS256","typ":"JWT"}`)) + "." +
		enc.EncodeToString([]byte(payload)) + "." +
		enc.EncodeToString([]byte("signature"))
}

func serve(t *testing.T, config *Config, header http.Header) (http.Header, http.Header) {
	t.Helper()
	var received http.Header
	next := http.HandlerFunc(func(rw http.ResponseWriter, req *http.Request) {
		received = req.Header.Clone()
		rw.Header().Set("Set-Cookie", "sat=x; Path=/")
		rw.Header().Set("Authorization", "Bearer response")
		rw.WriteHeader(http.StatusOK)
	})
	handler, err := New(context.Background(), next, config, "tokenfilter")
	if err != nil {
		t.Fatal(err)
	}
	req := httptest.NewRequest(http.MethodGet, "http://app.example.com/", nil)
	for name, values := range header {
		for _, value := range values {
			req.Header.Add(name, value)
		}
	}
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	return received, rec.Header()
}

func TestCookies(t *testing.T) {
	tests := []struct {
		name   string
		cookie []string
		want   []string
	}{
		{"no cookies", nil, nil},
		{"platform cookies only", []string{"sat=a; srt=b; dat=c; drt=d"}, nil},
		{"platform and own cookies", []string{"sat=a; auth=x; dat=c; theme=dark"}, []string{"auth=x; theme=dark"}},
		{"launchpad cookies", []string{"launchpad-token=a; launchpad-0123abcd-token=b; launchpad-0123abcd-code-verifier=c"}, []string{"launchpad-0123abcd-code-verifier=c"}},
		{"pattern is anchored", []string{"xlaunchpad-0123-token=a; launchpad-0123-tokenx=b; launchpad-xyz-token=c"}, []string{"xlaunchpad-0123-token=a; launchpad-0123-tokenx=b; launchpad-xyz-token=c"}},
		{"names are case sensitive", []string{"SAT=a; Dat=b"}, []string{"SAT=a; Dat=b"}},
		{"similar names are kept", []string{"sat_=a; satx=b; xsat=c"}, []string{"sat_=a; satx=b; xsat=c"}},
		{"values are kept as sent", []string{`auth="a b"; sat=x; raw=%7B%22k%22%3A1%7D; empty=`}, []string{`auth="a b"; raw=%7B%22k%22%3A1%7D; empty=`}},
		{"unchanged header is kept as sent", []string{"auth=x;theme=dark"}, []string{"auth=x;theme=dark"}},
		{"several cookie headers", []string{"sat=a; auth=x", "dat=b", "theme=dark"}, []string{"auth=x; theme=dark"}},
		{"cookie without value", []string{"sat; auth"}, []string{"auth"}},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			header := http.Header{}
			for _, c := range tt.cookie {
				header.Add("Cookie", c)
			}
			received, _ := serve(t, testConfig(), header)
			if got := received.Values("Cookie"); !reflect.DeepEqual(nilIfEmpty(got), tt.want) {
				t.Fatalf("cookie = %q, want %q", got, tt.want)
			}
		})
	}
}

func TestManyCookies(t *testing.T) {
	parts := []string{"sat=" + strings.Repeat("a", 1500), "dat=" + strings.Repeat("b", 1500)}
	var want []string
	for i := 0; i < 28; i++ {
		c := "c" + string(rune('a'+i%26)) + string(rune('a'+i/26)) + "=" + strings.Repeat("v", 150)
		parts = append(parts, c)
		want = append(want, c)
	}
	header := http.Header{}
	header.Set("Cookie", strings.Join(parts, "; "))
	received, _ := serve(t, testConfig(), header)
	if got := received.Get("Cookie"); got != strings.Join(want, "; ") {
		t.Fatalf("cookie = %q", got)
	}
}

func cookieParts(n int, prefix string) string {
	parts := make([]string, n)
	for i := range parts {
		parts[i] = prefix + strconv.Itoa(i) + "=v"
	}
	return strings.Join(parts, "; ")
}

func TestCookiePartsLimit(t *testing.T) {
	tests := []struct {
		name   string
		limit  int
		cookie []string
		want   []string
	}{
		{"default limit reached", 0, []string{"sat=a; " + cookieParts(299, "c")}, []string{cookieParts(299, "c")}},
		{"default limit exceeded", 0, []string{"sat=a; " + cookieParts(300, "c")}, nil},
		{"own cookies over the limit", 0, []string{cookieParts(301, "c")}, nil},
		{"empty parts are counted", 0, []string{"auth=x" + strings.Repeat(";", 301)}, nil},
		{"parts of several headers are counted", 0, []string{cookieParts(200, "a"), cookieParts(101, "b")}, nil},
		{"empty values are counted", 0, append(repeated("", 298), "sat=a; auth=x"), []string{"auth=x"}},
		{"empty values over the limit", 0, append(repeated("", 299), "sat=a; auth=x"), nil},
		{"only empty values over the limit", 0, repeated("", 301), nil},
		{"values over the limit", 0, repeated("auth=x", 301), nil},
		{"configured limit reached", 2, []string{"sat=a; auth=x"}, []string{"auth=x"}},
		{"configured limit exceeded", 2, []string{"sat=a; auth=x; theme=dark"}, nil},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			config := testConfig()
			config.MaxCookieParts = tt.limit
			header := http.Header{}
			for _, c := range tt.cookie {
				header.Add("Cookie", c)
			}
			received, _ := serve(t, config, header)
			if got := received.Values("Cookie"); !reflect.DeepEqual(nilIfEmpty(got), tt.want) {
				t.Fatalf("cookie has %d values, want %d", len(got), len(tt.want))
			}
		})
	}
}

func repeated(value string, n int) []string {
	values := make([]string, n)
	for i := range values {
		values[i] = value
	}
	return values
}

func TestAuthorizationValuesLimit(t *testing.T) {
	platformJWT := testJWT(`{"https://platform.neuromation.io/user":"alice"}`)
	tests := []struct {
		name  string
		limit int
		auth  []string
		want  []string
	}{
		{"default limit reached", 0, append(repeated("Basic dXNlcjpwYXNz", 7), "Bearer "+platformJWT), repeated("Basic dXNlcjpwYXNz", 7)},
		{"default limit exceeded", 0, repeated("Basic dXNlcjpwYXNz", 9), nil},
		{"empty values over the limit", 0, repeated("", 9), nil},
		{"configured limit reached", 1, []string{"Basic dXNlcjpwYXNz"}, []string{"Basic dXNlcjpwYXNz"}},
		{"configured limit exceeded", 1, []string{"Basic dXNlcjpwYXNz", "Bearer opaque-secret"}, nil},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			config := testConfig()
			config.MaxAuthorizationValues = tt.limit
			header := http.Header{}
			for _, a := range tt.auth {
				header.Add("Authorization", a)
			}
			received, _ := serve(t, config, header)
			if got := received.Values("Authorization"); !reflect.DeepEqual(nilIfEmpty(got), tt.want) {
				t.Fatalf("authorization has %d values, want %d", len(got), len(tt.want))
			}
		})
	}
}

func TestCreateConfigLimit(t *testing.T) {
	config := CreateConfig()
	if config.MaxCookieParts != 300 || config.MaxTokenLength != 16384 || config.MaxAuthorizationValues != 8 {
		t.Fatal("unexpected default limits")
	}
}

func TestJWTWithExtraSegments(t *testing.T) {
	token := testJWT(`{"identity":"alice"}`) + ".extra"
	header := http.Header{}
	header.Set("Authorization", "Bearer "+token)
	received, _ := serve(t, testConfig(), header)
	if received.Get("Authorization") != "Bearer "+token {
		t.Fatal("authorization changed")
	}
}

func benchmarkCookie(b *testing.B, cookie string) {
	handler, err := New(context.Background(), http.HandlerFunc(func(http.ResponseWriter, *http.Request) {}), testConfig(), "tokenfilter")
	if err != nil {
		b.Fatal(err)
	}
	rec := httptest.NewRecorder()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		req := httptest.NewRequest(http.MethodGet, "http://app.example.com/", nil)
		req.Header.Set("Cookie", cookie)
		handler.ServeHTTP(rec, req)
	}
}

func BenchmarkCookieLimit(b *testing.B) {
	benchmarkCookie(b, "sat=a; "+cookieParts(299, "c"))
}

func BenchmarkLargeBearer(b *testing.B) {
	handler, err := New(context.Background(), http.HandlerFunc(func(http.ResponseWriter, *http.Request) {}), testConfig(), "tokenfilter")
	if err != nil {
		b.Fatal(err)
	}
	value := "Bearer " + testJWT(`{"https://platform.neuromation.io/user":[`+strings.Repeat("0,", 350000)+`0]}`)
	rec := httptest.NewRecorder()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		req := httptest.NewRequest(http.MethodGet, "http://app.example.com/", nil)
		req.Header.Set("Authorization", value)
		handler.ServeHTTP(rec, req)
	}
}

func benchmarkHeaderLines(b *testing.B, name, value string, n int) {
	handler, err := New(context.Background(), http.HandlerFunc(func(http.ResponseWriter, *http.Request) {}), testConfig(), "tokenfilter")
	if err != nil {
		b.Fatal(err)
	}
	values := repeated(value, n)
	rec := httptest.NewRecorder()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		req := httptest.NewRequest(http.MethodGet, "http://app.example.com/", nil)
		req.Header[name] = values
		handler.ServeHTTP(rec, req)
	}
}

func BenchmarkManyAuthorizationLines(b *testing.B) {
	benchmarkHeaderLines(b, "Authorization", "x", 61000)
}

func BenchmarkManyAuthorizationFields(b *testing.B) {
	benchmarkHeaderLines(b, "Authorization", "x", 22000)
}

func BenchmarkManyEmptyCookieLines(b *testing.B) {
	benchmarkHeaderLines(b, "Cookie", "", 110000)
}

func BenchmarkCookieOneMegabyte(b *testing.B) {
	benchmarkCookie(b, strings.Repeat("a=1;", 1<<18))
}

func TestAuthorization(t *testing.T) {
	platformJWT := testJWT(`{"https://platform.neuromation.io/user":"alice","exp":1}`)
	identityJWT := testJWT(`{"identity":"alice"}`)
	bothJWT := testJWT(`{"identity":"alice","https://platform.neuromation.io/user":"alice"}`)
	otherJWT := testJWT(`{"sub":"alice","iss":"https://issuer.example.com"}`)
	tests := []struct {
		name string
		auth []string
		want []string
	}{
		{"no header", nil, nil},
		{"platform user claim", []string{"Bearer " + platformJWT}, nil},
		{"platform token with both claims", []string{"Bearer " + bothJWT}, nil},
		{"identity claim only", []string{"Bearer " + identityJWT}, []string{"Bearer " + identityJWT}},
		{"lower case scheme", []string{"bearer " + platformJWT}, nil},
		{"padded payload", []string{"Bearer " + padded(platformJWT)}, nil},
		{"other issuer", []string{"Bearer " + otherJWT}, []string{"Bearer " + otherJWT}},
		{"opaque bearer", []string{"Bearer opaque-secret"}, []string{"Bearer opaque-secret"}},
		{"basic", []string{"Basic dXNlcjpwYXNz"}, []string{"Basic dXNlcjpwYXNz"}},
		{"invalid payload", []string{"Bearer a.!!!.c"}, []string{"Bearer a.!!!.c"}},
		{"payload is not an object", []string{"Bearer " + testJWT(`["identity"]`)}, []string{"Bearer " + testJWT(`["identity"]`)}},
		{"claim in header part", []string{"Bearer " + headerClaimJWT()}, []string{"Bearer " + headerClaimJWT()}},
		{"token over the length limit", []string{"Bearer " + longJWT(16385)}, []string{"Bearer " + longJWT(16385)}},
		{"token at the length limit", []string{"Bearer " + longJWT(16384)}, nil},
		{"several headers", []string{"Bearer " + platformJWT, "Basic dXNlcjpwYXNz"}, []string{"Basic dXNlcjpwYXNz"}},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			header := http.Header{}
			for _, a := range tt.auth {
				header.Add("Authorization", a)
			}
			received, _ := serve(t, testConfig(), header)
			if got := received.Values("Authorization"); !reflect.DeepEqual(nilIfEmpty(got), tt.want) {
				t.Fatalf("authorization = %q, want %q", got, tt.want)
			}
		})
	}
}

func TestEmptyConfigFails(t *testing.T) {
	config := CreateConfig()
	config.MaxCookieParts = 10
	if _, err := New(context.Background(), http.NotFoundHandler(), config, "tokenfilter"); err == nil {
		t.Fatal("expected an error")
	}
}

func TestConfiguredTokenLength(t *testing.T) {
	config := testConfig()
	config.MaxTokenLength = 64
	token := testJWT(`{"https://platform.neuromation.io/user":"alice"}`)
	header := http.Header{}
	header.Set("Authorization", "Bearer "+token)
	received, _ := serve(t, config, header)
	if received.Get("Authorization") != "Bearer "+token {
		t.Fatal("authorization changed")
	}
}

func TestSingleListIsEnough(t *testing.T) {
	for _, config := range []*Config{
		{Cookies: []string{"sat"}},
		{CookiePatterns: []string{"sat"}},
		{BearerClaims: []string{"https://platform.neuromation.io/user"}},
	} {
		if _, err := New(context.Background(), http.NotFoundHandler(), config, "tokenfilter"); err != nil {
			t.Fatal(err)
		}
	}
}

func TestResponseHeadersKept(t *testing.T) {
	header := http.Header{}
	header.Set("Cookie", "sat=a")
	_, response := serve(t, testConfig(), header)
	if response.Get("Set-Cookie") != "sat=x; Path=/" || response.Get("Authorization") != "Bearer response" {
		t.Fatalf("response headers changed: %v", response)
	}
}

func TestOtherHeadersKept(t *testing.T) {
	header := http.Header{}
	header.Set("Cookie", "sat=a")
	header.Set("X-Auth-Request-Email", "alice@example.com")
	header.Set("X-Api-Key", "key")
	received, _ := serve(t, testConfig(), header)
	if received.Get("X-Auth-Request-Email") != "alice@example.com" || received.Get("X-Api-Key") != "key" {
		t.Fatalf("headers changed: %v", received)
	}
}

func TestInvalidPattern(t *testing.T) {
	config := testConfig()
	config.CookiePatterns = []string{"("}
	if _, err := New(context.Background(), http.NotFoundHandler(), config, "tokenfilter"); err == nil {
		t.Fatal("expected an error")
	}
}

func padded(token string) string {
	parts := strings.Split(token, ".")
	for len(parts[1])%4 != 0 {
		parts[1] += "="
	}
	return strings.Join(parts, ".")
}

func longJWT(length int) string {
	payload := `{"https://platform.neuromation.io/user":"alice","pad":"`
	for {
		token := testJWT(payload + `"}`)
		if len(token) >= length {
			return token
		}
		payload += "x"
	}
}

func TestLongJWTLength(t *testing.T) {
	for _, length := range []int{16384, 16385} {
		if got := len(longJWT(length)); got != length {
			t.Fatalf("token length = %d, want %d", got, length)
		}
	}
}

func headerClaimJWT() string {
	enc := base64.RawURLEncoding
	return enc.EncodeToString([]byte(`{"alg":"HS256","identity":"alice"}`)) + "." +
		enc.EncodeToString([]byte(`{"sub":"alice"}`)) + "." +
		enc.EncodeToString([]byte("signature"))
}

func nilIfEmpty(values []string) []string {
	if len(values) == 0 {
		return nil
	}
	return values
}
