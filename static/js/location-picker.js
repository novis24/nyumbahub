console.log('[LocationPicker] Script loaded');

// Simple initialization function
function initLocationPicker() {
  try {
    console.log('[LocationPicker] Attempting initialization...');
    
    const root = document.querySelector('[data-location-picker]');
    if (!root) {
      console.log('[LocationPicker] Element [data-location-picker] not found');
      return false;
    }
    
    console.log('[LocationPicker] Found root element');
    
    if (root._mapInitialized) {
      console.log('[LocationPicker] Already initialized');
      return true;
    }
    
    const errorBox = root.querySelector('[data-map-error]');
    const showError = message => {
      if (errorBox) {
        errorBox.textContent = message;
        errorBox.classList.remove('hidden');
      }
    };

    // Check required dependencies
    if (!root.dataset.apiKey) {
      console.error('[LocationPicker] Missing API key');
      showError('The map is unavailable because the Geoapify browser key is not configured on this server.');
      return false;
    }
    
    if (typeof L === 'undefined') {
      console.log('[LocationPicker] Leaflet library not available yet');
      return false;
    }
    
    console.log('[LocationPicker] Dependencies OK, initializing...');
    root._mapInitialized = true;
    
    const key = root.dataset.apiKey;
    const mapContainer = root.querySelector('[data-map]');
    const latInput = root.querySelector('[name=latitude]');
    const lngInput = root.querySelector('[name=longitude]');
    const locationInput = document.querySelector('[name=location]');
    
    // Validate elements exist
    if (!mapContainer) {
      console.error('[LocationPicker] Map container not found');
      root._mapInitialized = false;
      return false;
    }
    
    if (!latInput || !lngInput) {
      console.error('[LocationPicker] Latitude/longitude inputs not found');
      root._mapInitialized = false;
      return false;
    }
    
    // Create map
    console.log('[LocationPicker] Creating map...');
    const initial = (latInput.value && lngInput.value) 
      ? [Number(latInput.value), Number(lngInput.value)]
      : [-6.7924, 39.2083];
    
    const map = L.map(mapContainer).setView(initial, latInput.value ? 15 : 6);
    
    // Add tile layer
    L.tileLayer(
      `https://maps.geoapify.com/v1/tile/{mapStyle}/{z}/{x}/{y}.png?apiKey=${encodeURIComponent(key)}`,
      { 
        mapStyle: 'osm-bright',
        attribution: '© OpenStreetMap contributors, © Geoapify',
        maxZoom: 20 
      }
    ).addTo(map);
    
    // Add marker
    const marker = L.marker(initial, { draggable: true }).addTo(map);
    
    // Reverse geocoding
    async function reverse(lat, lng) {
      try {
        const url = `https://api.geoapify.com/v1/geocode/reverse?lat=${lat}&lon=${lng}&format=json&apiKey=${encodeURIComponent(key)}`;
        console.log('[LocationPicker] Reverse geocoding:', lat, lng);
        const response = await fetch(url);
        if (!response.ok) throw new Error(`Geoapify returned ${response.status}`);
        const data = await response.json();
        const result = data.results?.[0];
        if (result && locationInput) {
          locationInput.value = result.formatted || result.suburb || result.district || locationInput.value;
          console.log('[LocationPicker] Location updated:', locationInput.value);
        }
      } catch (e) {
        console.error('[LocationPicker] Reverse geocode error:', e);
      }
    }
    
    // Update location and inputs
    function select(lat, lng, label, doReverse = true) {
      console.log('[LocationPicker] Location selected:', { lat, lng, label });
      marker.setLatLng([lat, lng]);
      map.setView([lat, lng], 16);
      latInput.value = Number(lat).toFixed(6);
      lngInput.value = Number(lng).toFixed(6);
      if (label && locationInput) locationInput.value = label;
      if (doReverse) reverse(lat, lng).catch(e => console.error('[LocationPicker] Reverse error:', e));
    }
    
    // Map events
    map.on('click', e => {
      console.log('[LocationPicker] Map clicked');
      select(e.latlng.lat, e.latlng.lng);
    });
    
    marker.on('dragend', () => {
      console.log('[LocationPicker] Marker dragged');
      const p = marker.getLatLng();
      select(p.lat, p.lng);
    });
    
    // Geolocation button
    const geoBtn = root.querySelector('[data-map-geolocate]');
    if (geoBtn) {
      geoBtn.addEventListener('click', () => {
        console.log('[LocationPicker] Geolocation requested');
        if (!navigator.geolocation) {
          alert('Location services not supported');
          return;
        }
        navigator.geolocation.getCurrentPosition(
          p => {
            console.log('[LocationPicker] Location acquired');
            select(p.coords.latitude, p.coords.longitude);
          },
          err => {
            console.error('[LocationPicker] Geolocation error:', err);
            alert('Could not get your location. You can tap the map or search instead.');
          }
        );
      });
    }
    
    // Search functionality
    const searchBtn = root.querySelector('[data-map-search-button]');
    const searchInput = root.querySelector('[data-map-search]');
    const resultsBox = root.querySelector('[data-map-results]');
    
    if (searchBtn && searchInput && resultsBox) {
      async function doSearch() {
        const q = searchInput.value.trim();
        if (!q) return;
        
        try {
          console.log('[LocationPicker] Searching for:', q);
          const url = `https://api.geoapify.com/v1/geocode/search?text=${encodeURIComponent(q)}&filter=countrycode:tz&bias=countrycode:tz&format=json&limit=6&apiKey=${encodeURIComponent(key)}`;
          const response = await fetch(url);
          if (!response.ok) throw new Error(`Geoapify returned ${response.status}`);
          const data = await response.json();
          
          console.log('[LocationPicker] Search results:', data.results?.length ?? 0);
          
          resultsBox.innerHTML = '';
          if (!data.results?.length) {
            resultsBox.classList.add('hidden');
            return;
          }
          
          resultsBox.classList.remove('hidden');
          data.results.forEach(r => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'block w-full border-b border-n-100 p-3 text-left text-sm hover:bg-n-50';
            btn.textContent = r.formatted;
            btn.addEventListener('click', e => {
              e.preventDefault();
              console.log('[LocationPicker] Result selected:', r.formatted);
              select(r.lat, r.lon, r.formatted, false);
              resultsBox.classList.add('hidden');
            });
            resultsBox.appendChild(btn);
          });
        } catch (e) {
          console.error('[LocationPicker] Search error:', e);
          showError('Map search could not connect to Geoapify. Check the production API key and its allowed website domains.');
        }
      }
      
      searchBtn.addEventListener('click', doSearch);
      searchInput.addEventListener('keydown', e => {
        if (e.key === 'Enter') {
          e.preventDefault();
          doSearch();
        }
      });
    }
    
    // Fix map display
    setTimeout(() => {
      console.log('[LocationPicker] Invalidating map size');
      map.invalidateSize();
    }, 50);
    
    console.log('[LocationPicker] ✓ Initialization complete');
    return true;
    
  } catch (e) {
    console.error('[LocationPicker] Fatal error:', e, e.stack);
    return false;
  }
}

// Try to initialize
let initialized = false;
function tryInit() {
  if (!initialized && initLocationPicker()) {
    initialized = true;
    console.log('[LocationPicker] Successful initialization');
    return;
  }
}

// Wait for DOM and Leaflet
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    console.log('[LocationPicker] DOM ready, waiting for Leaflet...');
    // Try immediately
    tryInit();
    // Then keep trying until Leaflet loads
    const maxAttempts = 100;
    let attempts = 0;
    const timer = setInterval(() => {
      if (typeof L !== 'undefined') {
        console.log('[LocationPicker] Leaflet available!');
        tryInit();
        clearInterval(timer);
      } else if (attempts++ >= maxAttempts) {
        console.error('[LocationPicker] Leaflet never loaded');
        clearInterval(timer);
      }
    }, 50);
  });
} else {
  console.log('[LocationPicker] DOM already ready');
  tryInit();
  // Keep polling for Leaflet
  const maxAttempts = 100;
  let attempts = 0;
  const timer = setInterval(() => {
    if (typeof L !== 'undefined') {
      console.log('[LocationPicker] Leaflet available!');
      tryInit();
      clearInterval(timer);
    } else if (attempts++ >= maxAttempts) {
      console.error('[LocationPicker] Leaflet never loaded');
      clearInterval(timer);
    }
  }, 50);
}
