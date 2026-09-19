## Purpose

Provide a Sentinel-2-specific OPTRAM (Optical Path Length Adjusted Reflectance Model) soil-moisture proxy index, computable from surface reflectance bands, to extend the data-engine surface index library beyond Landsat-centric products.

## ADDED Requirements

### Requirement: OPTRAM surface index class
The `data_engine.surface.optram` module SHALL export an `OPTRAM` class with a `compute(cube: DataCube) -> DataCube` method that calculates the OPTRAM soil-moisture proxy using red and near-infrared reflectance values from the input cube, adding the result as a new band named `optram` with units `dimensionless` and range `[0, 1]` where higher values indicate wetter soil conditions.

#### Scenario: Compute OPTRAM from Sentinel-2 cube
- **WHEN** a DataCube containing `red` and `nir08` bands is passed to `OPTRAM().compute(cube)`
- **THEN** the cube gains an `optram` band with values in `[0, 1]` computed from the OPTRAM formula, and the band metadata includes `long_name="OPTRAM"`, `units="dimensionless"`, and `formula="sqrt(NIR / Red) * (1 - Red/NIR)"` or equivalent valid formulation

#### Scenario: Missing required bands
- **WHEN** a DataCube lacks either the `red` or `nir08` band
- **THEN** `compute()` raises `ValueError("Missing required band 'red' for OPTRAM")` or equivalent with the missing band name

#### Scenario: Invalid reflectance values
- **WHEN** input bands contain negative or NaN reflectance values
- **THEN** the OPTRAM output contains NaN for those pixels and finite values for valid pixels (no division-by-zero crash)

### Requirement: OPTRAM in vegetation index chain
The `VegetationIndices.compute()` method SHALL accept an optional `compute_optram: bool = False` parameter; when True it SHALL call `OPTRAM().compute(cube)` after all other indices and add the result to the cube.

#### Scenario: OPTRAM enabled in VegetationIndices
- **WHEN** `VegetationIndices(compute_optram=True).compute(cube)` is called with a cube containing red and NIR bands
- **THEN** the returned cube contains an `optram` band alongside NDVI, EVI, LAI, SAVI, and FVC
