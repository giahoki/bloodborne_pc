// Background of the launcher: a WebGL fragment shader (night sky, a pale moon with a blood-red
// halo, three layers of Yharnam-like spires and drifting fog) and a 2D layer of falling ash and
// embers. With the game's cover art behind it (body.with-art) the shader only draws fog and a
// vignette over the picture. Everything is procedural; no images are used.
(function () {
  'use strict';
  const VERT = 'attribute vec2 p; void main() { gl_Position = vec4(p, 0.0, 1.0); }';
  const FRAG = `
precision highp float;
uniform vec2 uRes;
uniform float uTime;
uniform float uArt;
uniform vec2 uMouse;

float hash(vec2 p) { p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }
float noise(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y);
}
float fbm(vec2 p) {
  float v = 0.0, a = 0.5;
  mat2 m = mat2(1.6, 1.2, -1.2, 1.6);
  for (int i = 0; i < 6; i++) { v += a * noise(p); p = m * p; a *= 0.5; }
  return v;
}
// A row of gothic buildings: bodies, buttresses and pointed spires, one per cell of x.
float skyline(vec2 uv, float scale, float seed, float base, float tall) {
  float x = uv.x * scale;
  float id = floor(x), fx = fract(x);
  float h = hash(vec2(id, seed));
  float w = 0.45 + 0.45 * hash(vec2(id, seed + 1.0));
  float top = base + h * h * tall;
  float body = step(abs(fx - 0.5), w * 0.5) * step(uv.y, top);
  // a stepped roof, then a needle spire on the taller ones
  float roof = step(abs(fx - 0.5), w * 0.3) * step(uv.y, top + 0.02);
  float spireH = (0.06 + 0.22 * hash(vec2(id, seed + 2.0))) * step(0.45, h);
  float k = clamp((uv.y - top - 0.02) / max(spireH, 1e-3), 0.0, 1.0);
  float spire = step(abs(fx - 0.5), w * 0.22 * (1.0 - k)) * step(top + 0.02, uv.y) * step(uv.y, top + 0.02 + spireH);
  // small side pinnacles
  float pin = step(abs(abs(fx - 0.5) - w * 0.42), 0.035 * (1.0 - clamp((uv.y - top) / 0.06, 0.0, 1.0)))
            * step(top, uv.y) * step(uv.y, top + 0.06) * step(0.3, h);
  // lit windows on the near rows
  return max(max(body, roof), max(spire, pin));
}

void main() {
  vec2 uv = gl_FragCoord.xy / uRes;
  float asp = uRes.x / uRes.y;
  vec2 p = vec2(uv.x * asp, uv.y);
  float t = uTime;
  vec2 par = (uMouse - 0.5) * vec2(0.02, 0.01);

  // sky: black at the top, a dull crimson glow near the horizon
  vec3 sky = mix(vec3(0.09, 0.03, 0.035), vec3(0.018, 0.012, 0.02), smoothstep(0.05, 0.85, uv.y));
  // the moon, upper right, with a blood halo and drifting cloud bands across it
  vec2 mc = vec2(asp * 0.74, 0.70) + par * 0.3;
  float d = length(p - mc);
  float r = 0.105;
  float disc = smoothstep(r, r - 0.004, d);
  float maria = fbm((p - mc) * 11.0 + 3.0);
  vec3 moon = mix(vec3(0.96, 0.92, 0.84), vec3(0.72, 0.66, 0.60), smoothstep(0.45, 0.75, maria));
  moon *= 0.85 + 0.15 * smoothstep(r, 0.0, d);
  float halo = exp(-max(d - r, 0.0) * 7.0) * 0.6 + exp(-max(d - r, 0.0) * 22.0) * 0.5;
  sky += vec3(0.55, 0.12, 0.09) * halo * 0.5;
  sky = mix(sky, moon, disc);
  float bands = fbm(vec2(p.x * 1.1 - t * 0.012, p.y * 4.0));
  float cloud = smoothstep(0.5, 0.78, bands) * smoothstep(0.35, 0.8, uv.y);
  sky = mix(sky, vec3(0.06, 0.035, 0.04) + vec3(0.25, 0.08, 0.06) * halo * 0.35, cloud * 0.88);

  vec3 col = sky;
  // far city, lit from behind by the moon
  float far = skyline(p + vec2(t * 0.0015, 0.0) + par * 0.4, 13.0, 3.0, 0.24, 0.14);
  col = mix(col, vec3(0.06, 0.028, 0.036) + vec3(0.3, 0.07, 0.05) * halo * 0.25, far * 0.7);
  float fog1 = fbm(p * vec2(1.3, 3.0) + vec2(t * 0.025, t * 0.004));
  col = mix(col, vec3(0.20, 0.11, 0.12), smoothstep(0.35, 0.85, fog1) * (1.0 - smoothstep(0.12, 0.5, uv.y)) * 0.65);
  // middle city
  vec2 mp = p + vec2(t * 0.003, 0.0) + par * 0.8;
  float mid = skyline(mp, 5.5, 11.0, 0.18, 0.2);
  col = mix(col, vec3(0.035, 0.018, 0.024), mid);
  // a few warm windows in the middle row, flickering like lamps
  vec2 cell = floor(mp * vec2(320.0, 150.0));
  float lit = step(0.992, hash(cell)) * mid * step(0.04, mp.y) * step(fract(mp.x * 320.0), 0.55);
  float flick = 0.7 + 0.3 * sin(t * (1.0 + hash(cell + 7.0) * 3.0) + hash(cell) * 40.0);
  col += vec3(0.85, 0.45, 0.18) * lit * flick * 0.55;
  // near rooftops, nearly black
  float near = skyline(p + vec2(t * 0.005, 0.0) + par * 1.4, 3.2, 23.0, 0.08, 0.16);
  col = mix(col, vec3(0.012, 0.007, 0.01), near);
  // ground fog rolling over everything
  float fog2 = fbm(p * vec2(1.8, 4.2) - vec2(t * 0.045, -t * 0.006));
  float fogAmt = smoothstep(0.38, 0.88, fog2) * (1.0 - smoothstep(0.0, 0.38, uv.y));
  col = mix(col, vec3(0.17, 0.10, 0.11), fogAmt * 0.75);

  float vig = smoothstep(1.25, 0.25, length((uv - vec2(0.55, 0.5)) * vec2(asp * 0.75, 1.0)));

  if (uArt > 0.5) {
    // over the cover art: fog, a crimson tint at the bottom, a vignette
    float f = fbm(p * vec2(1.4, 3.2) - vec2(t * 0.04, 0.0));
    float a = smoothstep(0.4, 0.9, f) * (1.0 - smoothstep(0.0, 0.55, uv.y)) * 0.55;
    vec3 tint = vec3(0.16, 0.06, 0.07);
    float shade = (1.0 - vig) * 0.85 + (1.0 - smoothstep(0.0, 0.35, uv.y)) * 0.35;
    float alpha = clamp(a + shade, 0.0, 0.92);
    vec3 c = mix(vec3(0.0), tint, a / max(alpha, 1e-3));
    gl_FragColor = vec4(c * alpha, alpha);
    return;
  }
  col *= mix(0.25, 1.0, vig);
  gl_FragColor = vec4(col, 1.0);
}`;

  const sky = document.getElementById('sky');
  const gl = sky.getContext('webgl', { premultipliedAlpha: true, alpha: true, antialias: false });
  let program, uniforms = {}, mouse = [0.5, 0.5], target = [0.5, 0.5];
  const scale = 0.6; // the shader is soft: render it below window resolution

  function compile(type, src) {
    const s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
    return s;
  }
  if (gl) {
    try {
      program = gl.createProgram();
      gl.attachShader(program, compile(gl.VERTEX_SHADER, VERT));
      gl.attachShader(program, compile(gl.FRAGMENT_SHADER, FRAG));
      gl.linkProgram(program);
      gl.useProgram(program);
      const buf = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
      const loc = gl.getAttribLocation(program, 'p');
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
      for (const name of ['uRes', 'uTime', 'uArt', 'uMouse']) uniforms[name] = gl.getUniformLocation(program, name);
    } catch (e) {
      console.error(e);
      program = null;
    }
  }

  // ash and embers
  const ash = document.getElementById('ash');
  const ctx = ash.getContext('2d');
  let flakes = [];
  function spawn(initial) {
    const ember = Math.random() < 0.12;
    return {
      x: Math.random() * ash.width, y: initial ? Math.random() * ash.height : -10,
      r: ember ? 0.8 + Math.random() * 1.4 : 0.6 + Math.random() * 1.8,
      vx: -0.15 + Math.random() * 0.35, vy: 0.18 + Math.random() * 0.5,
      a: 0.15 + Math.random() * 0.45, ember, phase: Math.random() * 6.28,
    };
  }
  function resize() {
    const w = window.innerWidth, h = window.innerHeight;
    sky.width = Math.max(2, Math.round(w * scale));
    sky.height = Math.max(2, Math.round(h * scale));
    ash.width = w; ash.height = h;
    const count = Math.round(w * h / 9000);
    flakes = Array.from({ length: count }, () => spawn(true));
  }
  window.addEventListener('resize', resize);
  window.addEventListener('mousemove', (e) => { target = [e.clientX / window.innerWidth, 1 - e.clientY / window.innerHeight]; });
  resize();

  const start = performance.now();
  let last = start;
  function frame(now) {
    const dt = Math.min(50, now - last) / 16.7;
    last = now;
    mouse[0] += (target[0] - mouse[0]) * 0.03;
    mouse[1] += (target[1] - mouse[1]) * 0.03;
    if (program) {
      gl.viewport(0, 0, sky.width, sky.height);
      gl.uniform2f(uniforms.uRes, sky.width, sky.height);
      gl.uniform1f(uniforms.uTime, (now - start) / 1000);
      gl.uniform1f(uniforms.uArt, document.body.classList.contains('with-art') ? 1 : 0);
      gl.uniform2f(uniforms.uMouse, mouse[0], mouse[1]);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    }
    ctx.clearRect(0, 0, ash.width, ash.height);
    for (const f of flakes) {
      f.phase += 0.01 * dt;
      f.x += (f.vx + Math.sin(f.phase) * 0.25) * dt;
      f.y += f.vy * dt * (f.ember ? -0.6 : 1);
      if (f.y > ash.height + 10 || f.y < -20 || f.x < -20 || f.x > ash.width + 20) {
        Object.assign(f, spawn(false));
        if (f.ember) f.y = ash.height + 5;
      }
      ctx.beginPath();
      ctx.arc(f.x, f.y, f.r, 0, 6.283);
      if (f.ember) {
        const flicker = 0.6 + 0.4 * Math.sin(f.phase * 7);
        ctx.fillStyle = `rgba(255, ${90 + 60 * flicker | 0}, 50, ${f.a * flicker})`;
        ctx.shadowColor = 'rgba(255, 60, 30, 0.9)';
        ctx.shadowBlur = 8;
      } else {
        ctx.fillStyle = `rgba(200, 188, 176, ${f.a * 0.6})`;
        ctx.shadowBlur = 0;
      }
      ctx.fill();
    }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
})();
