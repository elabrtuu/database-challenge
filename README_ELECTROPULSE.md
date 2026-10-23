# Case Study — Cross‑Market Consumer Electronics Catalog Unification

## Context
**ElectroPulse’s** core product, the **ElectroPulse Unified Catalog**, integrates consumer electronics data from many market catalogs, distributors, retail feeds, and compliance / regulatory sources worldwide.

Across the industry, the **model / trade name** is the primary point of reference for electronics stakeholders. Retailers, repair networks, customer support teams, reviewers, warranty providers, insurers, and enterprise procurement teams typically talk about devices in terms of their **model name**, not internal SKUs, supplier codes, or engineering identifiers.

For this reason, the **model / trade name is the central linking field** in the entire ElectroPulse Unified Catalog.
Yet model names are not standardized across countries or data providers, even when they refer to the same underlying product. Names often include **market‑specific spec strings**, **bundles**, **localized formatting**, and **reseller / importer suffixes**. This creates fragmentation and makes it difficult to provide a unified, global product view.

Your task is to design an approach that connects all relevant data through model / trade names across all ElectroPulse data sources, while preserving the original text from each source and maintaining relational integrity between **core components**, **manufacturers**, and **market metadata**.

## Objective
Develop a relational data model and an algorithm that allow ElectroPulse to:

1. Identify when different model / trade names refer to the same product, even if they appear in different countries or catalog systems.
2. Overcome challenges related to multilingual naming, bundle / combination products, generic naming patterns, imports / resellers, and combined catalog entries.
3. Preserve full traceability by keeping all original model names while also generating a canonical **model entity** that enables consistent linking.

Your deliverable is a relational data model and a matching approach for connecting the unified catalog through model / trade names, ensuring that all datasets can be unified around the naming conventions that matter most to consumer electronics stakeholders.

You will find in this repository **four datasets** from different countries: **Europe, the United States, Spain, and Switzerland**. Each dataset contains the variables **model / trade name (`model_name`)**, **core components (`core_components`)**, and **manufacturer‑of‑record (`manufacturer_of_record`)** (except for the Spain dataset, which does not contain **core components**). These datasets will serve as the basis for designing the relational model and matching algorithm.

---

## Useful Information

### Key Definitions

**Model / trade name (`model_name`)**  
The commercial model name of a device sold to customers.

**Core components (`core_components`)**  
Standardized technical identifiers (or component families) that help anchor a product’s technical identity.

**Manufacturer‑of‑record (`manufacturer_of_record`)**  
The company responsible for placing the product on the market in that source feed. It may represent the global OEM, a regional subsidiary, a licensing partner.

---

## Core Relationships in the Consumer Electronics Domain

### 1. Model name ↔ core components
- One component set can be marketed under many model names.
- A single model name can have multiple core components (multi‑component products).
- Multi‑component entries must be handled consistently even when markets format components differently.

### 2. Model name ↔ manufacturer‑of‑record
- The same underlying product may appear under slightly different manufacturer strings across markets due to subsidiaries, licensing, and distribution arrangements.
- Manufacturer helps disambiguate generic names and reseller / importer patterns.

**Illustrative example manufacturer variants**
- `ElectroPulse Devices Europe BV`
- `ElectroPulse Devices US LLC`
- `ElectroPulse Devices CH AG`
- `ElectroPulse Devices Iberia SL`

---

## Key Connection Challenges to Solve

### 1. Standard cleaning of irrelevant terms: specs, packaging, and market flags
Many `model_name` values include extra text that is not part of the true model / trade name (e.g., storage, connectivity, bundle flags, region tags).

**Examples**
- `Silver Kernel Beam 256GB Starter Kit Copperline` → `Silver Kernel Beam`
- `AzureRouter SE Ultra 64GB Starter Kit` → `AzureRouter SE Ultra`
- `AstraCam 512GB Dual‑SIM` → `AstraCam`
- `AuroraCam 1TB Starter Kit` → `AuroraCam`

Your solution should extract the base model while still retaining the raw strings for traceability.

---

### 2. Bundle / combination products listed as two model names together
Some entries represent bundles where two models are listed in a single field, using different separators:

**Examples from the datasets**
- `SolPhone Mini Ultra and CoreBook Pro Max`
- `SenseBook Plus and SparkDock`
- `RubyHub / VectorWatch Max Ultra 1TB Bundle`
- `BridgeRouter Max Lite / SilverDrive Plus`
- `HelioCam 1TB Dual‑SIM/SonicBuds Mini`
- `ZenithCam/TerraStand Mini Edge 1TB Refurbished/EchoPhone 256GB Dual‑SIM`
- `GoldenCam Ultra Ultra / QuantaLink Pro Plus`

A bundle should be matchable by either component product.
> Note: In this case study, the Europe feed is intentionally cleaner and does not include bundle / combination entries. Bundles appear in other markets.

---

### 3. Multilingual or market‑specific component aliases
Component names may vary by market language or local naming conventions, but should map to a single canonical component.

`component_list.json` provides the canonical **English** component vocabulary. Market feeds may contain localized variants that need to be normalized and mapped to this list.

**Examples from the datasets (Switzerland)**
- `Sierra Kern` → `Sierra Core` (German)
- `Magenta Bouclier Mesh` → `Magenta Shield Mesh` (French)
- `Slate Matriz` → `Slate Matrix` (Spanish)
- `Teal Lien` → `Teal Link` (French)
---

### 4. Inconsistent formatting of multi‑component lists
Multi‑component values in `core_components` can be formatted differently across sources:

**Examples from the datasets**
- `Slate Hub + Aero Flex`
- `Indigo Core; Lyra Kernel`
- `Magenta Kernel, Onyx Spark`
- `Sable Flow + Terra Wave Stack`
- `Coral Bouclier; Nova Node Stack`
- `Magenta Lien Gewebe & Sonic Bouclier Kernel`
- `Ruby Node Edge and Topaz Rayo`

Standardize multi‑component lists to a canonical delimiter of your choice (the key requirement is consistency).

---

### 5. “Generic” products — descriptor + manufacturer pattern
Some products are named generically, with the manufacturer appended in the model string:

**Examples from the datasets**
- `Atlas Fabric Kernel BlueRiver` → Atlas Fabric Kernel (core_component) + BlueRiver (manufacturer)
- `Delta Matrix Grid Copperline` → Delta Matrix Grid + Copperline
- `Silver Kernel Beam BlueRiver` → Silver Kernel Beam + BlueRiver
- `Copper Arc Windmill` → Copper Arc + Windmill
- `Vega Beam GoldenGate` → Vega Beam + GoldenGate

In these cases, the canonical product is typically the **core_component** (e.g., `Atlas Fabric Kernel`), and `manufacturer_of_record` helps disambiguate.