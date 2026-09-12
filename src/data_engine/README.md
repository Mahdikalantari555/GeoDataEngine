# METRIC ETa Pipeline

METRIC (Mapping Evapotranspiration with Internalized Calibration) Evapotranspiration estimation pipeline for Landsat data.

## Overview

This module implements the core METRIC algorithm for calculating evapotranspiration (ET) from satellite imagery using the surface energy balance approach.

## Energy Balance Equation

The surface energy balance is the foundation of the METRIC model:

$$R_n - G = H + LE$$

Where:
- $R_n$ = Net radiation (W/m²) - energy available
- $G$ = Soil heat flux (W/m²) - energy into ground
- $H$ = Sensible heat flux (W/m²) - energy heating the air
- $LE$ = Latent heat flux (W/m²) - energy used for evaporation

ET is computed from LE:

$$ET = \frac{LE}{\lambda}$$

Where $\lambda$ is the latent heat of vaporization (~2.45 MJ/kg).

## METRIC Algorithm Formulas

### 1. Net Radiation ($R_n$)

$$R_n = R_{s\downarrow} - R_{s\uparrow} + R_{l\downarrow} - R_{l\uparrow}$$

Where:
- $R_{s\downarrow}$ = Incoming shortwave radiation
- $R_{s\uparrow} = R_{s\downarrow} \times (1 - \alpha)$ = Reflected shortwave (albedo $\alpha$)
- $R_{l\downarrow}$ = Incoming longwave radiation
- $R_{l\uparrow} = \epsilon \sigma T_s^4$ = Outgoing longwave (emissivity $\epsilon$, Stefan-Boltzmann $\sigma$, surface temp $T_s$)

### 2. Soil Heat Flux ($G$)

$$G = R_n \times c_g$$

Where $c_g$ is an empirical coefficient based on vegetation indices:

$$c_g = 1.1 \times NDVI^3 - 1.0 \times NDVI^2 + 0.9 \times NDVI + 0.1$$

### 3. Sensible Heat Flux ($H$)

$$H = \rho c_p \frac{T_s - T_a}{r_{ah}}$$

Where:
- $\rho$ = air density (kg/m³)
- $c_p$ = specific heat of air (1.013 kJ/kg·K)
- $T_s$ = surface temperature (K)
- $T_a$ = air temperature (K)
- $r_{ah}$ = aerodynamic resistance to heat transfer (s/m)

### 4. Anchor Pixel Calibration

METRIC uses two reference pixels to calibrate the temperature difference relationship:

**Cold Pixel (Wet)**
- Well-watered vegetation or open water
- Expected ETrF ≈ 1.05
- $dT_{cold} = T_{s,cold} - T_a$

**Hot Pixel (Dry)**
- Dry bare soil or stressed vegetation
- Expected ETrF ≈ 0.05
- $dT_{hot} = T_{s,hot} - T_a$

The calibrated dT relationship:

$$dT = a \cdot T_s + b$$

Where:
$$a = \frac{dT_{hot} - dT_{cold}}{T_{s,hot} - T_{s,cold}}$$
$$b = dT_{cold} - a \cdot T_{s,cold}$$

### 5. ET Computation

**Step 1**: Calculate instantaneous LE from energy balance residual

$$LE = R_n - G - H$$

**Step 2**: Convert to instantaneous ET rate

$$ET_{inst} = \frac{LE}{\lambda} \times 3600 \quad (\text{mm/hr})$$

**Step 3**: Compute reference ET fraction

$$ETrF = \frac{ET_{inst}}{ETr_{inst}}$$

**Step 4**: Scale to daily ET

$$ET_{daily} = ETrF \times ETr_{daily}$$

## Surface Property Calculations

### Albedo ($\alpha$)

$$\alpha = 0.000275 \times (Blue + Red) - 0.2$$

### NDVI

$$NDVI = \frac{NIR - Red}{NIR + Red}$$

### Surface Emissivity ($\epsilon$)

$$\epsilon = 0.985 + 0.002 \times NDVI$$

### Roughness Length ($z_{0m}$)

$$z_{0m} = h \times e^{-2.5 \times (1 - NDVI)^{1.5}}$$

Where $h$ is vegetation height.

## Module Structure

```
metric_et/
├── pipeline/        # METRICPipeline class - main processing workflow
├── et/              # ET calculation modules (instantaneous, daily)
├── surface/         # Surface property calculations (albedo, NDVI, emissivity)
├── energy_balance/  # Energy balance components (Rn, G, H, LE)
├── calibration/     # Anchor pixel calibration (DTCalibration)
├── io/              # Input/output handling (Landsat, weather, Planetary Computer)
├── radiation/       # Radiation balance calculations
└── validation/      # Quality assessment and validation
```

## Usage

```python
from metric_et import METRICPipeline

# Initialize pipeline
pipeline = METRICPipeline(config={
    'calibration': {
        'method': 'hot-cold',
        'cold_etrf': 1.05,
        'hot_etrf': 0.05
    }
})

# Run processing
results = pipeline.run(
    landsat_dir='data/landsat_scene/',
    meteo_data={'temperature_2m': 25.0, 'wind_speed': 3.0},
    output_dir='output/'
)
```

## Output Products

| File | Description | Units |
|------|-------------|-------|
| ET_daily.tif | Daily evapotranspiration | mm/day |
| ET_inst.tif | Instantaneous ET at overpass | mm/hr |
| ETrF.tif | Reference ET fraction | - |
| LE.tif | Latent heat flux | W/m² |
| H.tif | Sensible heat flux | W/m² |
| Rn.tif | Net radiation | W/m² |
| G.tif | Soil heat flux | W/m² |
| dT.tif | Temperature difference | K |

## References

1. Allen, R.G., Tasumi, M., Trezza, R. (2007). "Satellite-based energy balance for mapping evapotranspiration with internalized calibration (METRIC) - Model." Journal of Irrigation and Drainage Engineering, 133(4), 380-394.

2. Allen, R.G., Tasumi, M., Morse, A., Trezza, R. (2007). "Satellite-based energy balance for mapping evapotranspiration with internalized calibration (METRIC) - Applications." Journal of Irrigation and Drainage Engineering, 133(4), 395-406.
