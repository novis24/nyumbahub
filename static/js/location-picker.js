(function () {
  const root = document.querySelector('[data-location-picker]');
  if (!root || !root.dataset.apiKey || typeof L === 'undefined') return;
  const key = root.dataset.apiKey;
  const latInput = root.querySelector('[name=latitude]');
  const lngInput = root.querySelector('[name=longitude]');
  const locationInput = document.querySelector('[name=location]');
  const initial = latInput.value && lngInput.value ? [Number(latInput.value), Number(lngInput.value)] : [-6.7924, 39.2083];
  const map = L.map(root.querySelector('[data-map]')).setView(initial, latInput.value ? 15 : 6);
  L.tileLayer(`https://maps.geoapify.com/v1/tile/{mapStyle}/{z}/{x}/{y}.png?apiKey=${encodeURIComponent(key)}`, {mapStyle:'osm-bright', attribution:'© OpenStreetMap contributors, © Geoapify', maxZoom:20}).addTo(map);
  const marker = L.marker(initial, {draggable:true}).addTo(map);
  async function reverse(lat, lng) {
    const response = await fetch(`https://api.geoapify.com/v1/geocode/reverse?lat=${lat}&lon=${lng}&format=json&apiKey=${encodeURIComponent(key)}`);
    const data = await response.json();
    const result = data.results && data.results[0];
    if (result && locationInput) locationInput.value = result.formatted || result.suburb || result.district || locationInput.value;
  }
  function select(lat, lng, label, doReverse=true) {
    marker.setLatLng([lat,lng]); map.setView([lat,lng], 16); latInput.value=Number(lat).toFixed(6); lngInput.value=Number(lng).toFixed(6);
    if (label && locationInput) locationInput.value=label;
    if (doReverse) reverse(lat,lng).catch(()=>{});
  }
  map.on('click', e => select(e.latlng.lat,e.latlng.lng));
  marker.on('dragend', () => { const p=marker.getLatLng(); select(p.lat,p.lng); });
  root.querySelector('[data-map-geolocate]').addEventListener('click', () => navigator.geolocation ? navigator.geolocation.getCurrentPosition(p=>select(p.coords.latitude,p.coords.longitude),()=>alert('We could not access your location. You can still search or tap the map.')) : alert('Location is not supported by this browser.'));
  const search = async () => {
    const q=root.querySelector('[data-map-search]').value.trim(); if(!q) return;
    const response=await fetch(`https://api.geoapify.com/v1/geocode/search?text=${encodeURIComponent(q)}&filter=countrycode:tz&bias=countrycode:tz&format=json&limit=6&apiKey=${encodeURIComponent(key)}`);
    const data=await response.json(), box=root.querySelector('[data-map-results]'); box.replaceChildren(); box.classList.toggle('hidden',!data.results?.length);
    (data.results||[]).forEach(r=>{const b=document.createElement('button');b.type='button';b.className='block w-full border-b border-n-100 p-3 text-left text-sm hover:bg-n-50';b.textContent=r.formatted;b.onclick=()=>{select(r.lat,r.lon,r.formatted,false);box.classList.add('hidden')};box.appendChild(b)});
  };
  root.querySelector('[data-map-search-button]').addEventListener('click',search);
  root.querySelector('[data-map-search]').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();search()}});
})();
