(() => {
  if (typeof window === 'undefined' || !window.AFRAME) {
    console.warn('[AFrame MCP] A-Frame runtime not detected. Bridge will not start.');
    return;
  }

  const BRIDGE_URL = window.AFRAME_MCP_BRIDGE_URL || 'ws://localhost:8765';
  const RETRY_DELAY_MS = 1500;
  const sceneEl = document.querySelector('a-scene');

  if (!sceneEl) {
    console.warn('[AFrame MCP] No <a-scene> element found, bridge inactive.');
    return;
  }

  const serializeVector = (vector) => {
    if (!vector) return null;
    return { x: vector.x, y: vector.y, z: vector.z };
  };

  const serializeEuler = (euler) => {
    if (!euler) return null;
    return { x: euler.x, y: euler.y, z: euler.z, order: euler.order };
  };

  const serializeEntity = (el) => {
    const attributes = {};
    if (el.getAttributeNames) {
      el.getAttributeNames().forEach((name) => {
        try {
          attributes[name] = el.getAttribute(name);
        } catch (err) {
          attributes[name] = String(el.getAttribute(name));
        }
      });
    }

    const object3D = el.object3D;
    const worldPosition = object3D ? serializeVector(object3D.getWorldPosition(new THREE.Vector3())) : null;
    const worldRotation = object3D ? serializeEuler(object3D.getWorldRotation(new THREE.Euler())) : null;
    const worldScale = object3D ? serializeVector(object3D.getWorldScale(new THREE.Vector3())) : null;

    return {
      tag: el.tagName.toLowerCase(),
      id: el.id || null,
      classList: Array.from(el.classList || []),
      attributes,
      children: Array.from(el.children || []).map(serializeEntity),
      worldPosition,
      worldRotation,
      worldScale,
    };
  };

  const ensureAssets = () => {
    let assets = sceneEl.querySelector('a-assets');
    if (!assets) {
      assets = document.createElement('a-assets');
      sceneEl.insertAdjacentElement('afterbegin', assets);
    }
    return assets;
  };

  const generateId = (prefix) => {
    const uid = Math.random().toString(36).slice(2, 9);
    return `${prefix}-${uid}`;
  };

  const handlers = {
    ping: async () => ({ status: 'ok' }),

    get_scene_graph: async () => {
      return { root: serializeEntity(sceneEl) };
    },

    find_entity: async ({ selector }) => {
      const el = sceneEl.querySelector(selector);
      if (!el) {
        return { exists: false };
      }
      return { exists: true, entity: serializeEntity(el) };
    },

    create_entity: async ({ tag, parentSelector = 'a-scene', attributes = {} }) => {
      const parent = sceneEl.matches(parentSelector)
        ? sceneEl
        : sceneEl.querySelector(parentSelector);
      if (!parent) {
        throw new Error(`Parent selector ${parentSelector} did not match any element`);
      }

      const el = document.createElement(tag);
      Object.entries(attributes).forEach(([key, value]) => {
        try {
          el.setAttribute(key, value);
        } catch (err) {
          el.setAttribute(key, typeof value === 'object' ? JSON.stringify(value) : value);
        }
      });

      if (!el.id) {
        el.id = generateId(tag);
      }

      parent.appendChild(el);
      return { createdId: el.id, entity: serializeEntity(el) };
    },

    update_component: async ({ selector, component, data }) => {
      const el = sceneEl.querySelector(selector);
      if (!el) {
        throw new Error(`Selector ${selector} did not match any entity`);
      }

      if (typeof data === 'object' && data !== null) {
        el.setAttribute(component, data);
      } else {
        el.setAttribute(component, data);
      }

      return { updated: true, entity: serializeEntity(el) };
    },

    remove_entity: async ({ selector }) => {
      const el = sceneEl.querySelector(selector);
      if (!el || el === sceneEl) {
        throw new Error('Cannot remove the root scene');
      }
      el.remove();
      return { removed: true };
    },

    load_remote_asset: async ({ assetId, assetType, url, options = {} }) => {
      const assets = ensureAssets();
      const id = assetId || generateId(assetType || 'asset');
      let node;

      switch (assetType) {
        case 'gltf':
        case 'model':
          node = document.createElement('a-asset-item');
          node.setAttribute('src', url);
          break;
        case 'image':
          node = document.createElement('img');
          node.setAttribute('src', url);
          break;
        case 'video':
          node = document.createElement('video');
          node.setAttribute('src', url);
          node.setAttribute('crossorigin', 'anonymous');
          break;
        case 'audio':
          node = document.createElement('audio');
          node.setAttribute('src', url);
          node.setAttribute('crossorigin', 'anonymous');
          break;
        default:
          node = document.createElement('a-asset-item');
          node.setAttribute('src', url);
      }

      Object.entries(options).forEach(([key, value]) => {
        node.setAttribute(key, value);
      });

      node.id = id;
      assets.appendChild(node);
      return { id, tag: node.tagName.toLowerCase(), src: url };
    },

    list_assets: async () => {
      const assets = ensureAssets();
      return {
        assets: Array.from(assets.children).map((child) => ({
          id: child.id || null,
          tag: child.tagName.toLowerCase(),
          src: child.getAttribute('src') || null,
        })),
      };
    },

    execute_script: async ({ code, parameters = {} }) => {
      const fn = new Function('AFRAME', 'scene', 'params', `'use strict';\n${code}`);
      const result = await Promise.resolve(fn(window.AFRAME, sceneEl, parameters));
      return { result };
    },

    capture_view: async ({ width = 1280, height = 720 }) => {
      const canvas = sceneEl.canvas || sceneEl.renderer?.domElement;
      if (!canvas) {
        throw new Error('Active canvas not available yet');
      }
      const prevWidth = canvas.width;
      const prevHeight = canvas.height;
      if (sceneEl.renderer && width && height) {
        sceneEl.renderer.setSize(width, height, false);
      }
      const dataUrl = canvas.toDataURL('image/png');
      if (sceneEl.renderer && prevWidth && prevHeight) {
        sceneEl.renderer.setSize(prevWidth, prevHeight, false);
      }
      const [, base64] = dataUrl.split(',');
      return { image: base64 };
    },

    focus_camera: async ({ selector }) => {
      const target = sceneEl.querySelector(selector);
      if (!target) {
        throw new Error(`Target ${selector} not found`);
      }
      const cameraEl = sceneEl.camera && sceneEl.camera.el ? sceneEl.camera.el : sceneEl.querySelector('[camera]');
      if (!cameraEl) {
        throw new Error('No camera available in the scene');
      }

      const box = new THREE.Box3().setFromObject(target.object3D);
      const center = box.getCenter(new THREE.Vector3());
      const size = box.getSize(new THREE.Vector3()).length();
      const distance = size > 0 ? size * 1.5 : 3;
      const offset = new THREE.Vector3(0, distance, distance);
      const position = center.clone().add(offset);

      cameraEl.object3D.position.copy(position);
      cameraEl.object3D.lookAt(center);
      cameraEl.object3D.updateMatrixWorld(true);
      return {
        cameraPosition: serializeVector(cameraEl.object3D.position),
        target: serializeVector(center),
      };
    },
  };

  const connect = () => {
    const socket = new WebSocket(BRIDGE_URL);

    socket.addEventListener('open', () => {
      socket.send(
        JSON.stringify({
          role: 'scene',
          sceneId: sceneEl.id || sceneEl.getAttribute('id') || 'scene',
        })
      );
    });

    socket.addEventListener('message', async (event) => {
      let message;
      try {
        message = JSON.parse(event.data);
      } catch (err) {
        console.warn('[AFrame MCP] Received invalid JSON message', event.data);
        return;
      }

      const { type, params = {}, requestId } = message;
      if (!type || !requestId) {
        console.warn('[AFrame MCP] Message missing type or requestId', message);
        return;
      }

      const handler = handlers[type];
      if (!handler) {
        socket.send(
          JSON.stringify({
            requestId,
            status: 'error',
            message: `No handler registered for ${type}`,
          })
        );
        return;
      }

      try {
        const result = await handler(params || {});
        socket.send(
          JSON.stringify({
            requestId,
            status: 'ok',
            result,
          })
        );
      } catch (error) {
        console.error('[AFrame MCP] Handler error', error);
        socket.send(
          JSON.stringify({
            requestId,
            status: 'error',
            message: error?.message || 'Unknown error executing handler',
          })
        );
      }
    });

    socket.addEventListener('close', () => {
      setTimeout(connect, RETRY_DELAY_MS);
    });

    socket.addEventListener('error', (err) => {
      console.error('[AFrame MCP] Bridge socket error', err);
      socket.close();
    });
  };

  if (sceneEl.hasLoaded) {
    connect();
  } else {
    sceneEl.addEventListener('loaded', connect, { once: true });
  }
})();
