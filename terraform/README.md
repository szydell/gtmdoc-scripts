# Terraform — mumps.pl infra

Infrastruktura AWS dla `mumps.pl`: S3 (Frankfurt) + CloudFront + ACM TLS + Route 53.

## Architektura

```
przeglądarka
    │  HTTPS mumps.pl
    ▼
CloudFront (edge, globalny)
    │  OAC sigv4
    ▼
S3 prod-mumps-pl  (eu-central-1 / Frankfurt)
```

- **S3** — wyłącznie prywatny, brak publicznego dostępu, szyfrowanie AES-256
- **OAC** (Origin Access Control) — CloudFront podpisuje requesty do S3; żaden inny podmiot nie może czytać bucketu
- **ACM** — certyfikat TLS w `us-east-1` (wymóg CloudFront), walidacja przez DNS automatycznie
- **Route 53** — hosted zone; rekordy A/AAAA (apex + www) jako aliasy CloudFront
- **PriceClass_100** — edge lokalizacje Europa + USA (najtańsza klasa, wystarczająca dla PL)

---

## Krok 0 — Konto AWS i profil CLI

### 0a. Utwórz IAM użytkownika (NIE używaj root credentials do Terraform)

1. Zaloguj się na root account → IAM → Users → **Create user**
2. Nazwa: `terraform-mumps`
3. Załącz politykę: `AdministratorAccess` (lub minimalną — patrz niżej)
4. Security credentials → **Create access key** → typ: *CLI*
5. Pobierz `Access Key ID` i `Secret Access Key`

> Minimalne uprawnienia zamiast AdministratorAccess:
> `AmazonS3FullAccess`, `CloudFrontFullAccess`, `AmazonRoute53FullAccess`,
> `AWSCertificateManagerFullAccess`, `IAMReadOnlyAccess`

### 0b. Dodaj profil do AWS CLI

```bash
aws configure --profile mumps-terraform
# AWS Access Key ID:     <wklej>
# AWS Secret Access Key: <wklej>
# Default region:        eu-central-1
# Default output format: json
```

Plik `~/.aws/credentials` (NIE commitować) otrzyma sekcję `[mumps-terraform]`.

### 0c. Weryfikacja profilu

```bash
aws sts get-caller-identity --profile mumps-terraform
# Zwróci Account ID, UserId, ARN — potwierdza poprawność kluczy
```

---

## Krok 1 — Inicjalizacja Terraform

```bash
cd terraform/
cp terraform.tfvars.example terraform.tfvars
# (terraform.tfvars jest w .gitignore — edytuj lokalnie)

terraform init
terraform validate
terraform plan
```

---

## Krok 2 — Apply

```bash
terraform apply
```

Apply trwa ~3–5 minut (ACM czeka na propagację DNS walidacji certyfikatu).

Po zakończeniu Terraform wypisze `route53_nameservers` — **4 serwery NS**.

---

## Krok 3 — Delegacja domeny do Route 53

> To jest jednorazowa czynność u Twojego rejestratora domeny.

**Co podać firmie / w panelu rejestratora:**

| Pole | Wartość (przykład, odczytaj z `terraform output`) |
|------|--------------------------------------------------|
| NS 1 | `ns-123.awsdns-45.com` |
| NS 2 | `ns-678.awsdns-90.net` |
| NS 3 | `ns-111.awsdns-22.co.uk` |
| NS 4 | `ns-999.awsdns-55.org` |

Zastąp **wszystkie** obecne rekordy NS dla `mumps.pl` powyższymi czterema.
Nie zmieniaj rekordów MX, jeśli masz e-mail na tej domenie — przepisz je ręcznie
do Route 53 przed zmianą NS (inaczej poczta przestanie działać na czas propagacji).

Propagacja DNS: zwykle kilka minut, max 48h (zależy od TTL starych NS).

```bash
# Sprawdź propagację (z zewnętrznego narzędzia lub lokalnie po cache flush):
dig NS mumps.pl +short
# Powinny pojawić się serwery awsdns-*
```

---

## Krok 4 — Wgranie treści do S3

Po `terraform apply` wgraj skompilowany Hugo site:

```bash
# Z katalogu gtmdoc-scripts/site/
hugo

# Wgraj do S3 (synchronizacja, usuwa nieistniejące pliki)
aws s3 sync public/ s3://prod-mumps-pl/ \
  --profile mumps-terraform \
  --delete \
  --cache-control "public, max-age=31536000, immutable"  # dla assets/
```

Inwalidacja cache CloudFront po każdym deploy:

```bash
aws cloudfront create-invalidation \
  --distribution-id $(terraform output -raw cloudfront_distribution_id) \
  --paths "/*" \
  --profile mumps-terraform
```

---

## Pliki w .gitignore (NIE commitować)

| Plik/katalog | Dlaczego tajny |
|---|---|
| `terraform.tfvars` | Może zawierać klucze / ID konta |
| `*.tfstate` | Stan infry — ujawnia ARN, IP, IDs |
| `.terraform/` | Lokalne pluginy providera |
| `.terraform.lock.hcl` | Można pominąć albo commitować (nieobowiązkowe) |

---

## Zmienne

| Zmienna | Domyślna | Opis |
|---|---|---|
| `aws_profile` | `mumps-terraform` | Profil AWS CLI |
| `aws_region` | `eu-central-1` | Region S3 (Frankfurt) |
| `domain_name` | `mumps.pl` | Domena apex |
| `bucket_name` | `prod-mumps-pl` | Nazwa bucketu S3 |
| `price_class` | `PriceClass_100` | Klasa cenowa CloudFront |

---

## Destroy

```bash
# Uwaga: usunie WSZYSTKIE zasoby włącznie z plikami w S3
terraform destroy
```
