---
title: User API
description: Use the CiteGuild user endpoint to verify API access and inspect safe profile details.
keywords: CiteGuild API, user API, profile API
---

# User API

Use the user endpoint to verify an API key and fetch safe account/profile details for the authenticated user.

## Authentication

```http
Authorization: Bearer ${{ api_key_env_var }}
```

Your API base URL is:

```text
{{ api_base_url }}
```

## Get current user

```http
GET {{ api_base_url }}/user
```

Example:

```bash
curl -H "Authorization: Bearer ${{ api_key_env_var }}" "{{ api_base_url }}/user"
```

Example response:

```json
{
  "email": "{{ user_email }}",
  "profile": {
    "state": "signed_up"
  }
}
```

The response does **not** include your API key or privileged admin flags.

## When to use this endpoint

- Check that an integration is authenticated correctly.
- Give an AI agent a low-risk connectivity test before it does product-specific work.
- Confirm which CiteGuild account a key belongs to.
