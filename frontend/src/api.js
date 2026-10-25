// Thin wrapper around the Flask API (proxied to :5001 by vite.config.js).
async function request(path, { method = 'GET', body } = {}) {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (res.status === 204) return null
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`)
  return data
}

export const api = {
  login: (username) => request('/users', { method: 'POST', body: { username } }),

  subjects: (userId) => request(`/users/${userId}/subjects`),
  createSubject: (userId, name) =>
    request(`/users/${userId}/subjects`, { method: 'POST', body: { name } }),
  deleteSubject: (id) => request(`/subjects/${id}`, { method: 'DELETE' }),
  createTopic: (subjectId, name, description) =>
    request(`/subjects/${subjectId}/topics`, { method: 'POST', body: { name, description } }),
  deleteTopic: (id) => request(`/topics/${id}`, { method: 'DELETE' }),

  conversations: (userId) => request(`/users/${userId}/conversations`),
  createConversation: (userId, topicId) =>
    request(`/users/${userId}/conversations`, { method: 'POST', body: { topic_id: topicId } }),
  conversation: (id) => request(`/conversations/${id}`),
  deleteConversation: (id) => request(`/conversations/${id}`, { method: 'DELETE' }),
  sendMessage: (id, content) =>
    request(`/conversations/${id}/messages`, { method: 'POST', body: { content } }),
  endConversation: (id, confidence) =>
    request(`/conversations/${id}/end`, { method: 'POST', body: { confidence } }),

  documents: (userId) => request(`/users/${userId}/documents`),
  createDocument: (userId, doc) =>
    request(`/users/${userId}/documents`, { method: 'POST', body: doc }),
  deleteDocument: (id) => request(`/documents/${id}`, { method: 'DELETE' }),

  progress: (userId) => request(`/users/${userId}/progress`),
}

export function topicOptions(subjects) {
  return subjects.flatMap((s) =>
    s.topics.map((t) => ({ id: t.id, label: `${s.name} / ${t.name}` })),
  )
}
