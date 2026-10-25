// Thin wrapper around the Flask API (proxied to :5001 by vite.config.js).
async function request(path, { method = 'GET', body } = {}) {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (res.status === 204) return null
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    // Signed out (or the sign-in expired) while using the app: App goes back to the picker
    if (res.status === 401 && !path.startsWith('/session')) {
      window.dispatchEvent(new Event('clutch:signed-out'))
    }
    const err = new Error(data.error || `Request failed (${res.status})`)
    err.status = res.status
    err.data = data
    throw err
  }
  return data
}

export const api = {
  profiles: () => request('/profiles'),
  session: () => request('/session'),
  signUp: (username, password) => request('/users', { method: 'POST', body: { username, password } }),
  // A profile made before passwords sends newPassword instead, to set one
  signIn: (username, password, newPassword) =>
    request('/session', { method: 'POST', body: { username, password, new_password: newPassword } }),
  signOut: () => request('/session', { method: 'DELETE' }),
  recoverPassword: (username, recoveryCode, newPassword) =>
    request('/session/recover', {
      method: 'POST',
      body: { username, recovery_code: recoveryCode, new_password: newPassword },
    }),

  subjects: (userId) => request(`/users/${userId}/subjects`),
  createSubject: (userId, name) =>
    request(`/users/${userId}/subjects`, { method: 'POST', body: { name } }),
  // A standard course from the catalog; topic (optional) is added inside it.
  addCourse: (userId, catalogId, topic) =>
    request(`/users/${userId}/subjects`, { method: 'POST', body: { catalog_id: catalogId, topic } }),
  linkSubject: (id, catalogId) =>
    request(`/subjects/${id}`, { method: 'PATCH', body: { catalog_id: catalogId } }),
  courses: () => request('/courses'),
  suggestCourses: (query) => request('/courses/suggest', { method: 'POST', body: { query } }),
  deleteSubject: (id) => request(`/subjects/${id}`, { method: 'DELETE' }),
  createTopic: (subjectId, name, description) =>
    request(`/subjects/${subjectId}/topics`, { method: 'POST', body: { name, description } }),
  deleteTopic: (id) => request(`/topics/${id}`, { method: 'DELETE' }),

  conversations: (userId) => request(`/users/${userId}/conversations`),
  createConversation: (userId, topicId) =>
    request(`/users/${userId}/conversations`, { method: 'POST', body: { topic_id: topicId } }),
  conversation: (id) => request(`/conversations/${id}`),
  deleteConversation: (id) => request(`/conversations/${id}`, { method: 'DELETE' }),
  sendMessage: (id, content, homework) =>
    request(`/conversations/${id}/messages`, { method: 'POST', body: { content, homework } }),
  endConversation: (id, confidence) =>
    request(`/conversations/${id}/end`, { method: 'POST', body: { confidence } }),

  documents: (userId, query = '') =>
    request(`/users/${userId}/documents${query ? `?q=${encodeURIComponent(query)}` : ''}`),
  document: (id) => request(`/documents/${id}`),
  createDocument: (userId, doc) =>
    request(`/users/${userId}/documents`, { method: 'POST', body: doc }),
  deleteDocument: (id) => request(`/documents/${id}`, { method: 'DELETE' }),
  readPages: (images, kind = 'homework') =>
    request('/homework/read', { method: 'POST', body: { images, kind } }),
  transcribe: (audio) => request('/lecture/transcribe', { method: 'POST', body: { audio } }),
  lectureNotes: (transcript) =>
    request('/lecture/notes', { method: 'POST', body: { transcript } }),
  studyGuide: (homework) =>
    request('/homework/study-guide', { method: 'POST', body: { homework } }),

  progress: (userId) => request(`/users/${userId}/progress`),

  events: (userId, from, to) =>
    request(`/users/${userId}/events?${new URLSearchParams({ from, to })}`),
  createEvent: (userId, event) => request(`/users/${userId}/events`, { method: 'POST', body: event }),
  updateEvent: (id, changes) => request(`/events/${id}`, { method: 'PATCH', body: changes }),
  deleteEvent: (id) => request(`/events/${id}`, { method: 'DELETE' }),
  // today and tz come from this browser so "today" and streaks follow the student's clock
  planner: (userId, today, tz) =>
    request(`/users/${userId}/planner?${new URLSearchParams({ today, tz })}`),

  startQuiz: (topicId) => request(`/topics/${topicId}/quiz`, { method: 'POST' }),
  quiz: (id) => request(`/quizzes/${id}`),
  submitQuiz: (id, answers) => request(`/quizzes/${id}/submit`, { method: 'POST', body: { answers } }),
  badges: (userId) => request(`/users/${userId}/badges`),
}

export function topicOptions(subjects) {
  return subjects.flatMap((s) =>
    s.topics.map((t) => ({
      id: t.id,
      label: `${s.name}${s.verification === 'verified' ? ' ✓' : s.verification === 'partial' ? ' ◐' : ''} / ${t.name}`,
    })),
  )
}
